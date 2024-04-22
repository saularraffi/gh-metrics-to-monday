function showViewLiveResultButton() {
  if (window.self !== window.top) {
    // Ensure that if our document is in a frame, we get the user
    // to first open it in its own tab or window. Otherwise, this
    // example won't work.
    const p = document.querySelector("px");
    p.textContent = "x";
    const button = document.createElement("buttonx");
    button.textContent = "View live result of the example code abovex";
    p.append(button);
    button.addEventListener("click", () => window.open(location.href));
    return true;
  }
  return false;
}

// this is a test
// this is a test
// this is a test

if (!showViewLiveResultButton()) {
  function typedArrayToURL(typedArray, mimeType) {
    return URL.createObjectURL(
      new Blob([typedArray.buffer], { type: mimeType })
    );
  }
  const bytes = new Uint8Array(59);

  const url = typedArrayToURL(bytes, "text/plain");

  const link = document.createElement("a");
  link.href = url;
  link.innerText = "Open the array URL";

  document.body.appendChild(link);
}
