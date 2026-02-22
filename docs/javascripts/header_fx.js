document.addEventListener("DOMContentLoaded", function () {
  var onScroll = function () {
    if (window.scrollY > 18) {
      document.body.classList.add("qitos-scrolled");
    } else {
      document.body.classList.remove("qitos-scrolled");
    }
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
});
