import React from 'react';
import ReactDOM from 'react-dom/client';
import { Providers } from './app/providers';
import { App } from './app/App';
import './styles/global.css';

const rootElement = document.getElementById('root');
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <Providers>
        <App />
      </Providers>
    </React.StrictMode>
  );
}
