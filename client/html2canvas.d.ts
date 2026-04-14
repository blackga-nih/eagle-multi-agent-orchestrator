declare module 'html2canvas' {
  interface Html2CanvasOptions {
    scale?: number;
    logging?: boolean;
    useCORS?: boolean;
    windowWidth?: number;
    windowHeight?: number;
  }

  export default function html2canvas(
    element: HTMLElement,
    options?: Html2CanvasOptions,
  ): Promise<HTMLCanvasElement>;
}
