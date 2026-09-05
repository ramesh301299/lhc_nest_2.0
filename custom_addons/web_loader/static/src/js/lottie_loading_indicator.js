/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { LoadingIndicator } from "@web/webclient/loading_indicator/loading_indicator";
import { useRef, useEffect } from "@odoo/owl";

/**
 * Plays the real Lottie animation inside Odoo's bottom-centre loading
 * indicator, instead of the "Loading" text label.
 *
 * The player is vendored at web_loader/static/lib/lottie/ rather than pulled
 * from unpkg.com: Odoo's backend runs under a CSP that blocks external script
 * hosts, so the <script src="https://unpkg.com/..."> form of the dotlottie
 * embed cannot work here. Files under static/lib are not wrapped as ES modules
 * by the asset pipeline, so the UMD bundle runs as a plain script and exposes
 * window.lottie. It is listed before this file in the manifest, so it has
 * already executed by the time this module is evaluated.
 */

const ANIMATION_PATH = "/web_loader/static/src/json/enmac_loader.json";

/**
 * The source composition is an 800x600 canvas with the dots occupying only a
 * part of it, so rendering it whole would leave the animation small and
 * off-centre. This crop is the animation's exact swept bounding box over the
 * full 33-frame loop, computed by sampling every transform rather than
 * estimated - the parent null carries three animated properties that all have
 * to be composed:
 *
 *   * scale  200%           (doubles both dot size and their spread)
 *   * rotate 0 -> 180 deg   (the whole cluster turns about the null)
 *   * position [460,304] -> [338,298]
 *
 * on top of each dot's own +/-30 travel and 75%->150% scale of r=10.4845.
 * Sampled result: x 288.4..510.5, y 107.0..363.2, padded by 8 units. The
 * cluster is therefore TALLER than it is wide (ratio ~0.875) because of the
 * rotation - loader.css must match that ratio or the dots clip.
 */
const VIEW_BOX = "280 98 239 273";

// Fetched once per session. The response is cached as *text* and re-parsed per
// player instance on purpose: lottie-web mutates the animation object it is
// given, so handing the same object to a second player corrupts the first.
let animationTextPromise = null;

function getAnimationData() {
    if (!animationTextPromise) {
        animationTextPromise = fetch(ANIMATION_PATH).then((response) => {
            if (!response.ok) {
                throw new Error(`web_loader: cannot load ${ANIMATION_PATH} (${response.status})`);
            }
            return response.text();
        });
    }
    return animationTextPromise.then((text) => JSON.parse(text));
}

patch(LoadingIndicator.prototype, {
    setup() {
        super.setup();
        this.lottieRef = useRef("lottie");

        // The indicator's markup is behind a t-if inside <Transition>, so the
        // element appears and disappears while the component itself stays
        // mounted. onMounted would therefore fire only once, before the element
        // exists; keying the effect on the ref's element is what makes the
        // player start and stop with every show/hide.
        useEffect(
            (el) => {
                if (!el || !window.lottie) {
                    return;
                }
                let animation = null;
                let cancelled = false;

                getAnimationData()
                    .then((animationData) => {
                        // The indicator may already have been hidden again by
                        // the time the first fetch resolves.
                        if (cancelled || !this.lottieRef.el) {
                            return;
                        }
                        animation = window.lottie.loadAnimation({
                            container: this.lottieRef.el,
                            renderer: "svg",
                            loop: true,
                            autoplay: true,
                            animationData,
                            rendererSettings: {
                                viewBoxSize: VIEW_BOX,
                                preserveAspectRatio: "xMidYMid meet",
                            },
                        });
                    })
                    .catch((error) => {
                        // A broken loader must never break the page it is
                        // reporting on; the CSS fallback still shows something.
                        console.warn(error);
                    });

                return () => {
                    cancelled = true;
                    if (animation) {
                        animation.destroy();
                    }
                };
            },
            () => [this.lottieRef.el]
        );
    },
});
