/**
 * LHC NEST — the loading overlay on the sign-in screen.
 *
 * The backend gets this overlay from `web.LoadingIndicator`, which watches the
 * RPC bus. The login page has no webclient and no RPCs: it is an ordinary form
 * POST followed by a full page load. So there is nothing to listen to, and the
 * few seconds between pressing "Log in" and the backend painting are exactly
 * the ones with no feedback at all.
 *
 * This puts the same overlay up on submit. It is deliberately tiny and has no
 * dependencies — the login bundle is the first thing served and should stay
 * that way.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.querySelector("form.oe_login_form");
        if (!form) {
            return;
        }

        form.addEventListener("submit", function () {
            // The browser blocks a second submit itself; this only guards
            // against stacking a second overlay on top of the first.
            if (document.querySelector(".lhc-loader")) {
                return;
            }

            var overlay = document.createElement("div");
            overlay.className = "o_loading_indicator lhc-loader";
            overlay.setAttribute("role", "status");
            overlay.setAttribute("aria-live", "polite");
            overlay.setAttribute("aria-busy", "true");
            overlay.innerHTML =
                '<div class="lhc-loader-box">' +
                    '<div class="lhc-loader-mark">' +
                        '<img src="/lhc_nest_theme/static/src/img/lhc_monogram.svg" alt=""/>' +
                        '<span class="lhc-loader-ring" aria-hidden="true"></span>' +
                    '</div>' +
                    '<div class="lhc-loader-text">Signing in' +
                        '<span class="lhc-loader-dots" aria-hidden="true"><i></i><i></i><i></i></span>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(overlay);
        });
    });
})();
