declare module "opensheetmusicdisplay" {
  export type OpenSheetMusicDisplayOptions = {
    autoResize?: boolean;
    drawingParameters?: string;
    drawTitle?: boolean;
    [k: string]: unknown;
  };

  export class OpenSheetMusicDisplay {
    constructor(container: HTMLElement, options?: OpenSheetMusicDisplayOptions);
    load(xml: string): Promise<void>;
    render(): Promise<void>;
  }
}

