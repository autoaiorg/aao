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

  // Mock HTMLCanvasElement.prototype.getContext for JSDOM
  if (typeof HTMLCanvasElement !== 'undefined') {
    HTMLCanvasElement.prototype.getContext = function (type: string) {
      if (type === '2d') {
        return {
          fillRect: () => {},
          clearRect: () => {},
          getImageData: () => ({ data: new Array(4) }),
          putImageData: () => {},
          createImageData: () => [],
          setTransform: () => {},
          drawImage: () => {},
          save: () => {},
          fillText: () => {},
          restore: () => {},
          beginPath: () => {},
          moveTo: () => {},
          lineTo: () => {},
          closePath: () => {},
          stroke: () => {},
          fill: () => {},
          arc: () => {},
          roundRect: () => {},
          createLinearGradient: () => ({ addColorStop: () => {} }),
          measureText: () => ({ width: 50 }),
        } as unknown as CanvasRenderingContext2D;
      }
      return null;
    } as unknown as typeof HTMLCanvasElement.prototype.getContext;
  }
}
