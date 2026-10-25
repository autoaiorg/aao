import '@testing-library/jest-dom/vitest';

// Polyfills or mocks if needed for testing environment
if (typeof window !== 'undefined') {
  // Mock matchMedia
  window.matchMedia = window.matchMedia || function (query) {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  };
}
