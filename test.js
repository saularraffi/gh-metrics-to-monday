function showViewLiveResultButton() {
  if (window.self !== window.top) {
    // Ensure that if our document is in a frame, we get the user
    // to first open it in its own tab or window. Otherwise, this
    // example won't work.
    const p = document.querySelector("p");
    p.textContent = "";
    const button = document.createElement("button");
    button.textContent = "View live result of the example code above";
    p.append(button);
    button.addEventListener("click", () => window.open(location.href));
    return true;
  }
  return false;
}

File.prototype.save = function (update) {
  update = typeof update === "undefined" ? true : update;
  if (Array.isArray(File.list)) {
    var index = File.indexOf(this);
    if (~index && update) {
      File.list[index] = this;
      console.warn(
        "File `%s` has been loaded before and updated now for: %O.",
        this.url,
        this
      );
    } else File.list.push(this);
    console.log(File.list);
  } else {
    File.list = [this];
  }
  return this;
};
