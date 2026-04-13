import { Viewer, Worker } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";

// Use the pdfjs version that ships with pdfjs-dist — pinned in package.json.
const PDFJS_VERSION = "3.11.174";

export function PdfViewer({ url }: { url: string }) {
  const layout = defaultLayoutPlugin();
  return (
    <div className="w-full h-full bg-stone-100">
      <Worker workerUrl={`https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.js`}>
        <Viewer fileUrl={url} plugins={[layout]} defaultScale={1.1} />
      </Worker>
    </div>
  );
}
