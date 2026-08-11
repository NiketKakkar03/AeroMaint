import { MinimalViewer } from "@aeromaint/react-minimal-viewer";

if (typeof MinimalViewer !== "function")
  throw new Error("MinimalViewer is not exported");
process.stdout.write("clean packed React consumer passed\n");
