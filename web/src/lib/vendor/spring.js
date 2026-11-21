/*
 * Vendored from https://github.com/Rene-Roscher/skills, plugins/web/skills/interface-motion/scripts/spring.mjs
 * (commit 211f216, lines 1-88: params, position, spring; CLI and self-test left out).
 * Copyright Rene Roscher. Licensed under the Apache License, Version 2.0: http://www.apache.org/licenses/LICENSE-2.0
 */
/**
 * Spring to CSS linear(). No dependencies; runs in Node and in the browser.
 *
 * Parameters follow Apple's spring model: a perceptual duration in seconds and a bounce from -1 to 1,
 * or the physics triplet stiffness, damping and mass. An optional release velocity is given in progress
 * units per second: the gesture's speed in px/s divided by the px the element still has to travel.
 *
 * The browser plays the result as an ordinary CSS transition. Nothing runs per frame.
 *
 *   node spring.mjs 0.35 0              duration, bounce
 *   node spring.mjs 0.35 0.2 --v 3      with a release velocity
 *   node spring.mjs --k 300 --d 24      stiffness, damping (mass 1)
 *   node spring.mjs --self-test         proves the math below
 */

/** Natural frequency w0 (rad/s) and damping ratio zeta. */
export function params({ duration, bounce = 0, stiffness, damping, mass = 1 } = {}) {
    if (stiffness !== undefined) {
        if (!(stiffness > 0) || !(damping >= 0) || !(mass > 0)) {
            throw new Error('stiffness and mass must be positive, damping at least 0');
        }
        return { w0: Math.sqrt(stiffness / mass), zeta: damping / (2 * Math.sqrt(stiffness * mass)) };
    }
    if (!(duration > 0)) {
        throw new Error('a duration in seconds, or stiffness and damping, is required');
    }
    if (!(bounce > -1 && bounce < 1)) {
        throw new Error('bounce must be between -1 and 1');
    }
    // Mass 1, stiffness (2 pi / duration)^2, damping ratio 1 - bounce (or 1 / (1 + bounce) below 0).
    return { w0: (2 * Math.PI) / duration, zeta: bounce >= 0 ? 1 - bounce : 1 / (1 + bounce) };
}

/** Progress x(t) from 0 to 1 with initial velocity v0 in progress units per second. */
export function position(w0, zeta, v0 = 0) {
    if (zeta < 1) {
        const wd = w0 * Math.sqrt(1 - zeta * zeta);
        return (t) => 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + ((zeta * w0 - v0) / wd) * Math.sin(wd * t));
    }
    if (zeta === 1) {
        return (t) => 1 - Math.exp(-w0 * t) * (1 + (w0 - v0) * t);
    }
    const s = w0 * Math.sqrt(zeta * zeta - 1);
    const r1 = -zeta * w0 + s;
    const r2 = -zeta * w0 - s;
    const c1 = (v0 + r2) / (r1 - r2);
    const c2 = -1 - c1;
    return (t) => 1 + c1 * Math.exp(r1 * t) + c2 * Math.exp(r2 * t);
}

/**
 * @returns {{ easing: string, ms: number, overshoot: number, duration: number, bounce: number }}
 *   easing: the linear() function. ms: time until the spring stays within 0.2 % of the target; use it as
 *   transition-duration. overshoot: the peak beyond the target as a fraction of the distance.
 *   duration and bounce: the same spring in Apple's terms.
 */
export function spring(options = {}) {
    const { w0, zeta } = params(options);
    const x = position(w0, zeta, options.velocity ?? 0);

    let settle = 0;
    let peak = 0;
    for (let t = 0; t <= 3; t += 1 / 240) {
        const value = x(t);
        if (Math.abs(1 - value) > 0.002) {
            settle = t;
        }
        peak = Math.max(peak, value);
    }
    settle = Math.max(settle, 0.08);

    const steps = Math.max(16, Math.min(72, Math.ceil(settle * 60)));
    const points = [];
    for (let i = 0; i <= steps; i++) {
        points.push(Math.round(x((i / steps) * settle) * 10000) / 10000);
    }
    points[0] = 0;
    points[steps] = 1;

    return {
        easing: `linear(${points.join(', ')})`,
        ms: Math.round(settle * 1000),
        overshoot: Math.max(0, peak - 1),
        duration: (2 * Math.PI) / w0,
        bounce: zeta <= 1 ? 1 - zeta : 1 / zeta - 1,
    };
}
