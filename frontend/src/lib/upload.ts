export const MAX_UPLOAD_MB = 20;

/** The problem with a picked file, in CR's words, or null when it can go to the server. */
export function checkPdf(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
    return `${file.name} isn't a PDF. Choose the broker's schedule as a .pdf file.`;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `${file.name} is larger than ${MAX_UPLOAD_MB} MB. Choose a smaller PDF.`;
  if (file.size === 0) return `${file.name} is empty. Choose another PDF.`;
  return null;
}
