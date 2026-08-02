/*
 * Mercato Foot — progressive-enhancement scroll reveal.
 *
 * Everything on the page is fully visible and usable with zero JS: the
 * stylesheet never hides [data-reveal] elements by default. This script
 * only *adds* a starting (invisible/offset) inline style right before it
 * starts observing, so there is no flash-of-hidden-content and no risk of
 * a broken layout if JS is disabled or fails to load.
 */
(function () {
  "use strict";

  var reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var targets = Array.prototype.slice.call(
    document.querySelectorAll("[data-reveal]")
  );

  if (!targets.length || reduceMotion || !("IntersectionObserver" in window)) {
    return;
  }

  targets.forEach(function (el, i) {
    el.style.transitionDelay = Math.min(i % 10, 10) * 40 + "ms";
    el.style.opacity = "0";
    el.style.transform = "translateY(16px)";
  });

  var io = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          el.style.opacity = "";
          el.style.transform = "";
          el.classList.add("is-revealed");
          io.unobserve(el);
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -10% 0px" }
  );

  targets.forEach(function (el) {
    io.observe(el);
  });

  document.documentElement.classList.add("has-js");
})();
