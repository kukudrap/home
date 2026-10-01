/* stub */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.boss = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";
  function mount(container, ctx) {
    var d = root.DK.ui.dom;
    container.appendChild(d.h("div.page", null, d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, ctx.t("nav.boss")), d.h("p", null, "stub")));
    return { destroy: function () {} };
  }
  return { mount: mount };
});
