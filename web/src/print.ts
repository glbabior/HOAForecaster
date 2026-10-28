/** Print the page – to paper or a PDF – with `title` as the document's title meanwhile, which
 * browsers offer as the PDF's file name. */
export function printAs(title: string): void {
  const before = document.title;
  document.title = title;
  const restore = () => {
    document.title = before;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  window.print();
}
