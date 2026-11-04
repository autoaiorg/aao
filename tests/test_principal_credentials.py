import pytest

from aao.principal_credentials import PrincipalDenied, authenticate, digest_token


def test_credential_digest_is_stable_and_not_plaintext():
    assert digest_token("secret") == digest_token("secret")
    assert digest_token("secret") != "secret"


@pytest.mark.parametrize("value,kind", [(None, "AUDITOR"), ("", "AGENT"), ("key", "CEO")])
def test_unauthorized_inputs_rejected_without_database(value, kind):
    with pytest.raises(PrincipalDenied):
        authenticate(value, kind=kind)


def test_development_principal_credentials_fail_closed_in_production(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "production")
    with pytest.raises(PrincipalDenied, match="unavailable"):
        authenticate("not-a-real-token", kind="AGENT")


@pytest.mark.parametrize(
    "fingerprint,kind",
    [
        (None, "AGENT"),
        ("A" * 64, "AGENT"),
        ("g" * 64, "AGENT"),
        ("a" * 64, "CEO"),
    ],
)
def test_mtls_identity_rejects_missing_or_malformed_identity_before_database(
    monkeypatch, fingerprint, kind,
):
    from aao import principal_credentials

    monkeypatch.setenv("AAO_ENV", "production")

    def database_access_is_forbidden():
        raise AssertionError("invalid mTLS identity must fail before database access")

    monkeypatch.setattr(principal_credentials, "connect_postgres", database_access_is_forbidden)
    with pytest.raises(PrincipalDenied):
        principal_credentials.authenticate_mtls(fingerprint, kind=kind)


def test_mtls_identity_resolves_enabled_unexpired_principal_and_digest(monkeypatch):
    from contextlib import contextmanager

    from aao import principal_credentials

    class Cursor:
        def execute(self, sql, params):
            assert "workload_identity_bindings" in sql
            assert "b.enabled=true" in sql
            assert "b.expires_at>clock_timestamp()" in sql
            assert "c.enabled=true" in sql
            assert "c.expires_at>clock_timestamp()" in sql
            assert params == ("a" * 64, "AGENT")
            return self

        def fetchone(self):
            return ("agent-1", "current-credential-digest")

    @contextmanager
    def connect():
        yield Cursor()

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(principal_credentials, "connect_postgres", connect)
    assert principal_credentials.authenticate_mtls("a" * 64, kind="AGENT") == (
        "agent-1",
        "current-credential-digest",
    )


def test_mtls_identity_rejects_unbound_or_disabled_principal(monkeypatch):
    from contextlib import contextmanager

    from aao import principal_credentials

    class Cursor:
        def execute(self, _sql, _params):
            return self

        def fetchone(self):
            return None

    @contextmanager
    def connect():
        yield Cursor()

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(principal_credentials, "connect_postgres", connect)
    with pytest.raises(PrincipalDenied, match="invalid or revoked"):
        principal_credentials.authenticate_mtls("a" * 64, kind="AGENT")


def test_production_worker_auth_uses_only_server_verified_mtls_scope(monkeypatch):
    from fastapi import Request

    from aao import principal_credentials
    from aao.uvicorn_mtls import MTLS_CLIENT_CERT_EXTENSION
    from aao.work_management_api import AuthenticatedPrincipal, require_worker

    fingerprint = "a" * 64
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(
        principal_credentials,
        "authenticate_mtls",
        lambda observed, *, kind: (
            ("agent-1", "db-digest")
            if observed == fingerprint and kind == "AGENT"
            else (_ for _ in ()).throw(AssertionError("untrusted identity was used"))
        ),
    )
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"x-agent-token", b"forged")],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8002),
            "extensions": {MTLS_CLIENT_CERT_EXTENSION: {"sha256": fingerprint}},
        }
    )

    principal = require_worker(request=request, x_agent_token="forged")

    assert principal == "agent-1"
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.token_digest == "db-digest"


def test_production_reader_preserves_fingerprint_for_transaction_recheck(monkeypatch):
    from fastapi import Request

    from aao import principal_credentials
    from aao.uvicorn_mtls import MTLS_CLIENT_CERT_EXTENSION
    from aao.work_management_api import read_principal, require_grant

    fingerprint = "b" * 64
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(
        principal_credentials,
        "authenticate_mtls",
        lambda observed, *, kind: ("agent-1", "db-digest")
        if observed == fingerprint and kind == "AGENT"
        else pytest.fail("reader used an untrusted identity"),
    )
    rechecks = []
    monkeypatch.setattr(
        principal_credentials,
        "authenticate_mtls_in_transaction",
        lambda db, observed, **kwargs: rechecks.append((observed, kwargs)) or True,
    )

    request = Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "https", "path": "/", "raw_path": b"/",
        "query_string": b"", "headers": [], "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 8002),
        "extensions": {MTLS_CLIENT_CERT_EXTENSION: {"sha256": fingerprint}},
    })
    principal = read_principal(request=request)

    class Db:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, _args):
            self.sql = sql
            return self

        def fetchone(self):
            if "FROM principal_credentials" in self.sql:
                return ("AGENT", True)
            return (1,)

    require_grant(Db(), principal, "project-1", "work.create")

    assert rechecks == [(
        fingerprint,
        {"principal_id": "agent-1", "token_digest": "db-digest", "kind": "AGENT"},
    )]


def test_production_bearer_without_verified_mtls_is_rejected(monkeypatch):
    from fastapi import HTTPException, Request

    from aao import principal_credentials
    from aao.work_management_api import require_worker

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(
        principal_credentials, "authenticate_mtls",
        lambda fingerprint, *, kind: (_ for _ in ()).throw(
            PrincipalDenied("Workload identity required")
        ) if fingerprint is None and kind == "AGENT" else pytest.fail("bad identity"),
    )
    request = Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "https", "path": "/", "raw_path": b"/",
        "query_string": b"", "headers": [(b"x-agent-token", b"otherwise-valid-bearer")],
        "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8002),
        "extensions": {},
    })
    with pytest.raises(HTTPException) as denied:
        require_worker(request=request, x_agent_token="otherwise-valid-bearer")
    assert denied.value.status_code == 403


def test_mtls_identity_is_revalidated_and_locked_in_mutation_transaction(monkeypatch):
    from aao.principal_credentials import authenticate_mtls_in_transaction

    monkeypatch.setenv("AAO_ENV", "production")

    class Db:
        def __init__(self, row):
            self.row = row
            self.query = None
            self.params = None

        def execute(self, query, params):
            self.query, self.params = query, params
            return self

        def fetchone(self):
            return self.row

    active = Db(("agent-1", "current-digest"))
    assert authenticate_mtls_in_transaction(
        active, "a" * 64, principal_id="agent-1",
        token_digest="current-digest", kind="AGENT",
    )
    assert "FOR SHARE OF b,c" in active.query
    assert "b.revoked_at IS NULL" in active.query
    assert "b.enabled=true" in active.query and "c.enabled=true" in active.query
    assert active.params == ("a" * 64, "agent-1", "AGENT")

    # If revocation committed before the operation acquires its row locks,
    # the binding no longer matches and the protected mutation must abort.
    revoked = Db(None)
    with pytest.raises(PrincipalDenied, match="invalid or revoked"):
        authenticate_mtls_in_transaction(
            revoked, "a" * 64, principal_id="agent-1",
            token_digest="current-digest", kind="AGENT",
        )


def test_transactional_development_credentials_fail_closed_in_production(monkeypatch):
    from aao.principal_credentials import authenticate_in_transaction

    monkeypatch.setenv("AAO_ENV", "production")
    with pytest.raises(PrincipalDenied, match="unavailable"):
        authenticate_in_transaction(object(), "not-a-real-token", kind="AUDITOR")


def test_project_grant_inventory_rejects_non_ceo_before_database_access(monkeypatch):
    from fastapi.testclient import TestClient

    from aao.work_management_api import app

    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setenv("AAO_CEO_TOKEN", "expected-ceo-token")
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects/example/grants",
            headers={"X-CEO-Token": "not-the-ceo"},
        )
    assert response.status_code == 403


def test_mandate_inventory_rejects_non_ceo_before_database_access(monkeypatch):
    from fastapi.testclient import TestClient

    from aao.work_management_api import app

    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setenv("AAO_CEO_TOKEN", "expected-ceo-token")
    with TestClient(app) as client:
        response = client.get(
            "/v1/mandates", headers={"X-CEO-Token": "not-the-ceo"},
        )
    assert response.status_code == 403


@pytest.mark.parametrize("environment", [None, "", "production", "prodution"])
@pytest.mark.parametrize("transactional", [False, True])
def test_individual_credentials_require_explicit_known_dev_environment(
    monkeypatch, environment, transactional,
):
    from aao import principal_credentials

    if environment is None:
        monkeypatch.delenv("AAO_ENV", raising=False)
    else:
        monkeypatch.setenv("AAO_ENV", environment)

    def database_access_is_forbidden():
        raise AssertionError("environment denial must happen before database access")

    monkeypatch.setattr(principal_credentials, "connect_postgres", database_access_is_forbidden)
    with pytest.raises(PrincipalDenied, match="unavailable"):
        if transactional:
            principal_credentials.authenticate_in_transaction(
                object(), "not-a-real-token", kind="AUDITOR",
            )
        else:
            principal_credentials.authenticate("not-a-real-token", kind="AGENT")


def test_grant_contract_accepts_execution_capabilities_only_as_exact_values():
    from datetime import UTC, datetime, timedelta

    from pydantic import ValidationError

    from aao.work_management_api import GrantRequest

    grant = GrantRequest(principal_id="agent-1", capability="execution.claim")
    assert grant.capability == "execution.claim"
    expiry = datetime.now(UTC) + timedelta(hours=4)
    assert GrantRequest(
        principal_id="agent-1", capability="execution.claim", expires_at=expiry,
    ).expires_at == expiry
    with pytest.raises(ValidationError, match="timezone"):
        GrantRequest(
            principal_id="agent-1",
            capability="execution.claim",
            expires_at=datetime.now(),
        )
    with pytest.raises(ValidationError, match="future"):
        GrantRequest(
            principal_id="agent-1",
            capability="execution.claim",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    assert GrantRequest(
        principal_id="auditor-1", capability="execution.reconcile"
    ).capability == "execution.reconcile"
    assert GrantRequest(
        principal_id="auditor-1", capability="effect.reconcile"
    ).capability == "effect.reconcile"
    for invalid in (
        "execution.claim.other", "execution.reconcile.extra",
        "effect.reconcile.extra", "work.create.extra", "credential.issue_publisher",
    ):
        with pytest.raises(ValidationError):
            GrantRequest(principal_id="agent-1", capability=invalid)


def test_grant_contract_accepts_only_enumerated_organizational_operations():
    from pydantic import ValidationError

    from aao.work_management_api import GrantRequest

    operations = (
        "organization.squad.create_temporary",
        "organization.squad.dissolve",
        "organization.slot.assign",
        "organization.unit.create_permanent",
        "organization.unit.merge",
        "organization.unit.split",
    )
    assert [
        GrantRequest(principal_id="agent-1", capability=operation).capability
        for operation in operations
    ] == list(operations)
    for invalid in (
        "organization.squad.create_temporary.extra",
        "organization.unit.delete",
        "organization.security.change",
        "organization.mission.change",
        "constitution.change",
        "authority.expand",
    ):
        with pytest.raises(ValidationError):
            GrantRequest(principal_id="agent-1", capability=invalid)


def test_shared_development_headers_are_not_accepted(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import read_principal, require_reviewer, require_worker

    monkeypatch.setenv("AAO_WORK_TOKEN", "dev-worker")
    monkeypatch.setenv("AAO_REVIEW_TOKEN", "dev-auditor")
    for call in (
        lambda: require_worker(x_agent_token=None),
        lambda: require_reviewer(x_auditor_token=None),
        lambda: read_principal(x_ceo_token=None, x_agent_token=None),
    ):
        with pytest.raises(HTTPException) as denied:
            call()
        assert denied.value.status_code == 403


def test_individual_reader_cannot_fall_back_to_shared_credential(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import read_principal

    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setattr("aao.principal_credentials.authenticate", lambda *_args, **_kwargs: (_ for _ in ()).throw(PrincipalDenied("invalid")))
    with pytest.raises(HTTPException) as denied:
        read_principal(x_ceo_token=None, x_agent_token="invalid-individual-token")
    assert denied.value.status_code == 403


class _GrantQuery:
    def __init__(self, principal_row):
        self.principal_row = principal_row
        self.queries = []

    def execute(self, sql, args):
        self.queries.append((sql, args))
        return self

    def fetchone(self):
        sql, _args = self.queries[-1]
        if "FROM principal_credentials" in sql:
            return self.principal_row
        return (1,)


def test_grant_rechecks_principal_inside_transaction(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import AuthenticatedPrincipal, require_grant

    principal = AuthenticatedPrincipal("agent-1", "agent-digest", "AGENT")
    for record in (None, ("AGENT", False), ("AUDITOR", True)):
        db = _GrantQuery(record)
        with pytest.raises(HTTPException) as exc:
            require_grant(db, principal, "project-1", "work.create")
        assert exc.value.status_code == 403
        assert len(db.queries) == 1
        assert "FOR SHARE" in db.queries[0][0]

    active = _GrantQuery(("AGENT", True))
    require_grant(active, principal, "project-1", "work.create")
    assert len(active.queries) == 2
    assert active.queries[0][1] == ("agent-1", "agent-digest")
    assert active.queries[1][1] == ("agent-1", "project-1", "work.create")


def test_reviewer_grant_requires_individual_auditor_kind():
    from fastapi import HTTPException

    from aao.work_management_api import AuthenticatedPrincipal, require_grant

    with pytest.raises(HTTPException) as exc:
        require_grant(
            _GrantQuery(("AGENT", True)),
            AuthenticatedPrincipal("agent-1", "agent-digest", "AGENT"),
            "project-1", "work.review",
        )
    assert exc.value.status_code == 403
    db = _GrantQuery(("AUDITOR", True))
    require_grant(
        db, AuthenticatedPrincipal("auditor-1", "auditor-digest", "AUDITOR"),
        "project-1", "work.review",
    )
    assert len(db.queries) == 2


def test_legacy_shared_principal_has_no_grant_authority(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import require_grant

    with pytest.raises(HTTPException) as exc:
        require_grant(_GrantQuery(None), "development-worker", "project-1", "work.create")
    assert exc.value.status_code == 403


def test_project_listing_rechecks_active_reader_in_transaction(monkeypatch):
    from contextlib import contextmanager

    from fastapi import HTTPException

    from aao import work_management_api
    from aao.principal_credentials import PrincipalDenied

    class ReaderDb:
        def __init__(self, row):
            self.row = row
            self.queries = []

        def execute(self, query, args=None):
            self.queries.append((query, args))
            return self

        def fetchone(self):
            return self.row

        def fetchall(self):
            return []

    def transaction_for(selected_db):
        @contextmanager
        def fake_tx():
            yield selected_db

        return fake_tx

    def authenticate(db, principal, *, kind):
        db.execute("SELECT principal credential FOR SHARE", (str(principal),))
        row = db.fetchone()
        if not row or row != (kind, True):
            raise PrincipalDenied("invalid or revoked")
        return str(principal)

    monkeypatch.setattr(
        "aao.principal_credentials.authenticate_identity_in_transaction", authenticate,
    )

    for record in (None, ("AGENT", False), ("AUDITOR", True)):
        db = ReaderDb(record)
        monkeypatch.setattr(work_management_api, "tx", transaction_for(db))
        with pytest.raises(HTTPException) as denied:
            work_management_api.projects(principal=work_management_api.AuthenticatedPrincipal(
                "agent-1", "agent-digest", "AGENT",
            ))
        assert denied.value.status_code == 403
        assert len(db.queries) == 1
        assert "FOR SHARE" in db.queries[0][0]

    active = ReaderDb(("AGENT", True))

    @contextmanager
    def active_tx():
        yield active

    monkeypatch.setattr(work_management_api, "tx", active_tx)
    principal = work_management_api.AuthenticatedPrincipal(
        "agent-1", "agent-digest", "AGENT",
    )
    assert work_management_api.projects(principal=principal) == []
    assert len(active.queries) == 2
    assert active.queries[0][1] == ("agent-1",)
    assert active.queries[1][1] == ("agent-1",)


@pytest.mark.parametrize(
    "environment", ["production", " PRODUCTION ", "prodution", None],
)
def test_static_ceo_bearer_is_unavailable_outside_development(monkeypatch, environment):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from starlette.requests import Request

    from aao.work_management_api import app, read_principal, require_ceo

    if environment is None:
        monkeypatch.delenv("AAO_ENV", raising=False)
    else:
        monkeypatch.setenv("AAO_ENV", environment)
    monkeypatch.setenv("AAO_CEO_TOKEN", "development-ceo-token")
    request = Request({
        "type": "http", "headers": [], "method": "GET", "scheme": "http",
        "server": ("testserver", 80), "client": ("testclient", 123),
        "path": "/", "query_string": b"", "root_path": "",
    })
    with pytest.raises(HTTPException) as direct:
        require_ceo(request=request, x_ceo_token="development-ceo-token")
    assert direct.value.status_code == 503

    with pytest.raises(HTTPException) as reader:
        read_principal(
            x_ceo_token="development-ceo-token", x_agent_token=None,
        )
    assert reader.value.status_code == 403

    with TestClient(app) as client:
        response = client.post(
            "/v1/mandates",
            headers={"X-CEO-Token": "development-ceo-token"},
            json={"title": "Must be denied", "objective": "Test only"},
        )
    assert response.status_code == 503
    with TestClient(app) as client:
        response = client.get(
            "/v1/projects", headers={"X-CEO-Token": "development-ceo-token"},
        )
    assert response.status_code == 403


def test_agent_named_ceo_is_not_treated_as_ceo_reader(monkeypatch):
    from contextlib import contextmanager

    from aao import work_management_api

    class ReaderDb:
        def __init__(self):
            self.queries = []

        def execute(self, query, args=None):
            self.queries.append((query, args))
            return self

        def fetchone(self):
            return ("AGENT", True)

        def fetchall(self):
            return []

    db = ReaderDb()

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(work_management_api, "tx", fake_tx)
    principal = work_management_api.AuthenticatedPrincipal("ceo", "ceo-digest", "AGENT")
    assert work_management_api.projects(principal=principal) == []
    assert len(db.queries) == 2
    assert "principal_credentials" in db.queries[0][0]
    assert "project_grants" in db.queries[1][0]
