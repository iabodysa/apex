// Copyright (c) 2026, AFMCO and contributors
// [#shared-icons]
// Single source of truth for every portal's inline-SVG icon geometry (lucide
// paths). Each export is the ordered child-element list for one glyph, consumed by
// @shared/components/IconBase.vue. Portals import ONLY the names they use (named
// exports keep tree-shaking intact, so a portal bundles only its own subset), then
// map their local icon name -> the geometry in a thin src/components/Icon.vue.
//
// Where two portals drew the SAME name with DIFFERENT geometry (e.g. a filled vs
// outline calendar), each variant kept its own export (numeric suffix) so no
// portal's appearance changed when the geometry was centralised. GENERATED — do
// not hand-edit; regenerate from the portal Icon.vue sources.
export const alert = [
  { tag: "path", attrs: { "d": "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" } },
  { tag: "path", attrs: { "d": "M12 9v4" } },
  { tag: "path", attrs: { "d": "M12 17h.01" } },
];
export const arrowLeft = [
  { tag: "path", attrs: { "d": "m12 19-7-7 7-7" } },
  { tag: "path", attrs: { "d": "M19 12H5" } },
];
export const badge = [
  { tag: "path", attrs: { "d": "M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z" } },
  { tag: "path", attrs: { "d": "m9 12 2 2 4-4" } },
];
export const banknote = [
  { tag: "rect", attrs: { "width": "20", "height": "12", "x": "2", "y": "6", "rx": "2" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "2" } },
  { tag: "path", attrs: { "d": "M6 12h.01M18 12h.01" } },
];
export const bed = [
  { tag: "path", attrs: { "d": "M2 4v16" } },
  { tag: "path", attrs: { "d": "M2 8h18a2 2 0 0 1 2 2v10" } },
  { tag: "path", attrs: { "d": "M2 17h20" } },
  { tag: "path", attrs: { "d": "M6 8v9" } },
];
export const bell = [
  { tag: "path", attrs: { "d": "M10.268 21a2 2 0 0 0 3.464 0" } },
  { tag: "path", attrs: { "d": "M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326" } },
];
export const bike = [
  { tag: "circle", attrs: { "cx": "18.5", "cy": "17.5", "r": "3.5" } },
  { tag: "circle", attrs: { "cx": "5.5", "cy": "17.5", "r": "3.5" } },
  { tag: "circle", attrs: { "cx": "15", "cy": "5", "r": "1" } },
  { tag: "path", attrs: { "d": "M12 17.5V14l-3-3 4-3 2 3h2" } },
];
export const box = [
  { tag: "path", attrs: { "d": "M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" } },
  { tag: "path", attrs: { "d": "m3.3 7 8.7 5 8.7-5" } },
  { tag: "path", attrs: { "d": "M12 22V12" } },
];
export const briefcase = [
  { tag: "rect", attrs: { "width": "20", "height": "14", "x": "2", "y": "7", "rx": "2", "ry": "2" } },
  { tag: "path", attrs: { "d": "M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" } },
];
export const building = [
  { tag: "path", attrs: { "d": "M10 12h4" } },
  { tag: "path", attrs: { "d": "M10 8h4" } },
  { tag: "path", attrs: { "d": "M14 21v-3a2 2 0 0 0-4 0v3" } },
  { tag: "path", attrs: { "d": "M6 10H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2" } },
  { tag: "path", attrs: { "d": "M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" } },
];
export const building2 = [
  { tag: "rect", attrs: { "width": "16", "height": "20", "x": "4", "y": "2", "rx": "2" } },
  { tag: "path", attrs: { "d": "M9 22v-4h6v4" } },
  { tag: "path", attrs: { "d": "M8 6h.01" } },
  { tag: "path", attrs: { "d": "M16 6h.01" } },
  { tag: "path", attrs: { "d": "M8 10h.01" } },
  { tag: "path", attrs: { "d": "M16 10h.01" } },
  { tag: "path", attrs: { "d": "M8 14h.01" } },
  { tag: "path", attrs: { "d": "M16 14h.01" } },
];
export const bus = [
  { tag: "path", attrs: { "d": "M8 6v6" } },
  { tag: "path", attrs: { "d": "M15 6v6" } },
  { tag: "path", attrs: { "d": "M2 12h19.6" } },
  { tag: "path", attrs: { "d": "M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3" } },
  { tag: "circle", attrs: { "cx": "7", "cy": "18", "r": "2" } },
  { tag: "path", attrs: { "d": "M9 18h5" } },
  { tag: "circle", attrs: { "cx": "16", "cy": "18", "r": "2" } },
];
export const calendar = [
  { tag: "path", attrs: { "d": "M8 2v4" } },
  { tag: "path", attrs: { "d": "M16 2v4" } },
  { tag: "rect", attrs: { "width": "18", "height": "18", "x": "3", "y": "4", "rx": "2" } },
  { tag: "path", attrs: { "d": "M3 10h18" } },
];
export const calendar2 = [
  { tag: "path", attrs: { "d": "M8 2v4" } },
  { tag: "path", attrs: { "d": "M16 2v4" } },
  { tag: "rect", attrs: { "width": "18", "height": "18", "x": "3", "y": "4", "rx": "2" } },
  { tag: "path", attrs: { "d": "M3 10h18" } },
  { tag: "path", attrs: { "d": "m9 16 2 2 4-4" } },
];
export const car = [
  { tag: "path", attrs: { "d": "M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" } },
  { tag: "circle", attrs: { "cx": "7", "cy": "17", "r": "2" } },
  { tag: "path", attrs: { "d": "M9 17h6" } },
  { tag: "circle", attrs: { "cx": "17", "cy": "17", "r": "2" } },
];
export const card = [
  { tag: "rect", attrs: { "width": "18", "height": "14", "x": "3", "y": "5", "rx": "2" } },
  { tag: "path", attrs: { "d": "M3 10h18" } },
  { tag: "path", attrs: { "d": "M7 15h2" } },
  { tag: "path", attrs: { "d": "M13 15h4" } },
];
export const chartColumn = [
  { tag: "path", attrs: { "d": "M3 3v16a2 2 0 0 0 2 2h16" } },
  { tag: "path", attrs: { "d": "M18 17V9" } },
  { tag: "path", attrs: { "d": "M13 17V5" } },
  { tag: "path", attrs: { "d": "M8 17v-3" } },
];
export const check = [
  { tag: "path", attrs: { "d": "M20 6 9 17l-5-5" } },
];
export const chevron = [
  { tag: "path", attrs: { "d": "m9 18 6-6-6-6" } },
];
export const circleCheck = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "path", attrs: { "d": "m9 12 2 2 4-4" } },
];
export const circleDashed = [
  { tag: "path", attrs: { "d": "M10.1 2.18a9.93 9.93 0 0 1 3.8 0" } },
  { tag: "path", attrs: { "d": "M17.6 3.71a9.95 9.95 0 0 1 2.69 2.7" } },
  { tag: "path", attrs: { "d": "M21.82 10.1a9.93 9.93 0 0 1 0 3.8" } },
  { tag: "path", attrs: { "d": "M20.29 17.6a9.95 9.95 0 0 1-2.7 2.69" } },
  { tag: "path", attrs: { "d": "M13.9 21.82a9.94 9.94 0 0 1-3.8 0" } },
  { tag: "path", attrs: { "d": "M6.4 20.29a9.95 9.95 0 0 1-2.69-2.7" } },
  { tag: "path", attrs: { "d": "M2.18 13.9a9.93 9.93 0 0 1 0-3.8" } },
  { tag: "path", attrs: { "d": "M3.71 6.4a9.95 9.95 0 0 1 2.7-2.69" } },
];
export const circleDot = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "1" } },
];
export const circlePause = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "line", attrs: { "x1": "10", "x2": "10", "y1": "15", "y2": "9" } },
  { tag: "line", attrs: { "x1": "14", "x2": "14", "y1": "15", "y2": "9" } },
];
export const clipboardCheck = [
  { tag: "rect", attrs: { "width": "8", "height": "4", "x": "8", "y": "2", "rx": "1", "ry": "1" } },
  { tag: "path", attrs: { "d": "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" } },
  { tag: "path", attrs: { "d": "m9 14 2 2 4-4" } },
];
export const clipboardList = [
  { tag: "rect", attrs: { "width": "8", "height": "4", "x": "8", "y": "2", "rx": "1", "ry": "1" } },
  { tag: "path", attrs: { "d": "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" } },
  { tag: "path", attrs: { "d": "M12 11h4" } },
  { tag: "path", attrs: { "d": "M12 16h4" } },
  { tag: "path", attrs: { "d": "M8 11h.01" } },
  { tag: "path", attrs: { "d": "M8 16h.01" } },
];
export const clock = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "polyline", attrs: { "points": "12 6 12 12 16 14" } },
];
export const crash = [
  { tag: "path", attrs: { "d": "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z" } },
];
export const dashboard = [
  { tag: "rect", attrs: { "width": "7", "height": "9", "x": "3", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "5", "x": "14", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "9", "x": "14", "y": "12", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "5", "x": "3", "y": "16", "rx": "1" } },
];
export const doc = [
  { tag: "path", attrs: { "d": "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" } },
  { tag: "path", attrs: { "d": "M14 2v5h5" } },
  { tag: "path", attrs: { "d": "M8 13h8" } },
  { tag: "path", attrs: { "d": "M8 17h8" } },
];
export const door = [
  { tag: "path", attrs: { "d": "M13 4h3a2 2 0 0 1 2 2v14" } },
  { tag: "path", attrs: { "d": "M2 20h3" } },
  { tag: "path", attrs: { "d": "M13 20h9" } },
  { tag: "path", attrs: { "d": "M10 12v.01" } },
  { tag: "path", attrs: { "d": "M13 4.562v16.157a1 1 0 0 1-1.242.97L5 20V5.562a2 2 0 0 1 1.515-1.94l4-1A2 2 0 0 1 13 4.561Z" } },
];
export const download = [
  { tag: "path", attrs: { "d": "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" } },
  { tag: "polyline", attrs: { "points": "7 10 12 15 17 10" } },
  { tag: "line", attrs: { "x1": "12", "x2": "12", "y1": "15", "y2": "3" } },
];
export const external = [
  { tag: "path", attrs: { "d": "M15 3h6v6" } },
  { tag: "path", attrs: { "d": "M10 14 21 3" } },
  { tag: "path", attrs: { "d": "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" } },
];
export const filter = [
  { tag: "polygon", attrs: { "points": "22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" } },
];
export const flag = [
  { tag: "path", attrs: { "d": "M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" } },
  { tag: "line", attrs: { "x1": "4", "x2": "4", "y1": "22", "y2": "15" } },
];
export const fuel = [
  { tag: "path", attrs: { "d": "M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 4 0v-6.998a2 2 0 0 0-.59-1.42L18 5" } },
  { tag: "path", attrs: { "d": "M14 21V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v16" } },
  { tag: "path", attrs: { "d": "M2 21h13" } },
  { tag: "path", attrs: { "d": "M3 9h11" } },
];
export const fuel2 = [
  { tag: "line", attrs: { "x1": "3", "x2": "15", "y1": "22", "y2": "22" } },
  { tag: "line", attrs: { "x1": "4", "x2": "14", "y1": "9", "y2": "9" } },
  { tag: "path", attrs: { "d": "M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18" } },
  { tag: "path", attrs: { "d": "M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2 2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 5" } },
];
export const funnel = [
  { tag: "path", attrs: { "d": "M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z" } },
];
export const gauge = [
  { tag: "path", attrs: { "d": "m12 14 4-4" } },
  { tag: "path", attrs: { "d": "M3.34 19a10 10 0 1 1 17.32 0" } },
];
export const globe = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "path", attrs: { "d": "M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" } },
  { tag: "path", attrs: { "d": "M2 12h20" } },
];
export const hammer = [
  { tag: "path", attrs: { "d": "m15 12-9.373 9.373a1 1 0 0 1-3.001-3L12 9" } },
  { tag: "path", attrs: { "d": "m18 15 4-4" } },
  { tag: "path", attrs: { "d": "m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172v-.344a2 2 0 0 0-.586-1.414l-1.657-1.657A6 6 0 0 0 12.516 3H9l1.243 1.243A6 6 0 0 1 12 8.485V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5" } },
];
export const help = [
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "10" } },
  { tag: "path", attrs: { "d": "m4.93 4.93 4.24 4.24" } },
  { tag: "path", attrs: { "d": "m14.83 9.17 4.24-4.24" } },
  { tag: "path", attrs: { "d": "m14.83 14.83 4.24 4.24" } },
  { tag: "path", attrs: { "d": "m9.17 14.83-4.24 4.24" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "4" } },
];
export const home = [
  { tag: "path", attrs: { "d": "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" } },
  { tag: "path", attrs: { "d": "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" } },
];
export const home2 = [
  { tag: "path", attrs: { "d": "m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" } },
  { tag: "polyline", attrs: { "points": "9 22 9 12 15 12 15 22" } },
];
export const idCard = [
  { tag: "path", attrs: { "d": "M16 10h2" } },
  { tag: "path", attrs: { "d": "M16 14h2" } },
  { tag: "path", attrs: { "d": "M6.17 15a3 3 0 0 1 5.66 0" } },
  { tag: "circle", attrs: { "cx": "9", "cy": "11", "r": "2" } },
  { tag: "rect", attrs: { "x": "2", "y": "5", "width": "20", "height": "14", "rx": "2" } },
];
export const image = [
  { tag: "rect", attrs: { "width": "18", "height": "18", "x": "3", "y": "3", "rx": "2", "ry": "2" } },
  { tag: "circle", attrs: { "cx": "9", "cy": "9", "r": "2" } },
  { tag: "path", attrs: { "d": "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" } },
];
export const key = [
  { tag: "path", attrs: { "d": "M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z" } },
  { tag: "circle", attrs: { "cx": "16.5", "cy": "7.5", "r": ".5", "fill": "currentColor" } },
];
export const layers = [
  { tag: "path", attrs: { "d": "m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" } },
  { tag: "path", attrs: { "d": "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65" } },
  { tag: "path", attrs: { "d": "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" } },
];
export const layoutGrid = [
  { tag: "rect", attrs: { "width": "7", "height": "7", "x": "3", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "7", "x": "14", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "7", "x": "14", "y": "14", "rx": "1" } },
  { tag: "rect", attrs: { "width": "7", "height": "7", "x": "3", "y": "14", "rx": "1" } },
];
export const list = [
  { tag: "path", attrs: { "d": "M3 5h.01" } },
  { tag: "path", attrs: { "d": "M3 12h.01" } },
  { tag: "path", attrs: { "d": "M3 19h.01" } },
  { tag: "path", attrs: { "d": "M8 5h13" } },
  { tag: "path", attrs: { "d": "M8 12h13" } },
  { tag: "path", attrs: { "d": "M8 19h13" } },
];
export const loader = [
  { tag: "path", attrs: { "d": "M12 2v4" } },
  { tag: "path", attrs: { "d": "m16.2 7.8 2.9-2.9" } },
  { tag: "path", attrs: { "d": "M18 12h4" } },
  { tag: "path", attrs: { "d": "m16.2 16.2 2.9 2.9" } },
  { tag: "path", attrs: { "d": "M12 18v4" } },
  { tag: "path", attrs: { "d": "m4.9 19.1 2.9-2.9" } },
  { tag: "path", attrs: { "d": "M2 12h4" } },
  { tag: "path", attrs: { "d": "m4.9 4.9 2.9 2.9" } },
];
export const lock = [
  { tag: "rect", attrs: { "width": "18", "height": "11", "x": "3", "y": "11", "rx": "2", "ry": "2" } },
  { tag: "path", attrs: { "d": "M7 11V7a5 5 0 0 1 10 0v4" } },
];
export const lockOpen = [
  { tag: "rect", attrs: { "width": "18", "height": "11", "x": "3", "y": "11", "rx": "2", "ry": "2" } },
  { tag: "path", attrs: { "d": "M7 11V7a5 5 0 0 1 9.9-1" } },
];
export const mail = [
  { tag: "path", attrs: { "d": "m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7" } },
  { tag: "rect", attrs: { "x": "2", "y": "4", "width": "20", "height": "16", "rx": "2" } },
];
export const message = [
  { tag: "path", attrs: { "d": "M7.9 20A9 9 0 1 0 4 16.1L2 22Z" } },
];
export const minus = [
  { tag: "path", attrs: { "d": "M5 12h14" } },
];
export const packageGlyph = [
  { tag: "path", attrs: { "d": "M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z" } },
  { tag: "path", attrs: { "d": "M12 22V12" } },
  { tag: "polyline", attrs: { "points": "3.29 7 12 12 20.71 7" } },
  { tag: "path", attrs: { "d": "m7.5 4.27 9 5.15" } },
];
export const packageGlyph2 = [
  { tag: "path", attrs: { "d": "M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z" } },
  { tag: "path", attrs: { "d": "M12 22V12" } },
  { tag: "path", attrs: { "d": "m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7" } },
  { tag: "path", attrs: { "d": "m7.5 4.27 9 5.15" } },
];
export const pencil = [
  { tag: "path", attrs: { "d": "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" } },
  { tag: "path", attrs: { "d": "m15 5 4 4" } },
];
export const phone = [
  { tag: "path", attrs: { "d": "M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384" } },
];
export const phone2 = [
  { tag: "path", attrs: { "d": "M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92Z" } },
];
export const pin = [
  { tag: "path", attrs: { "d": "M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "10", "r": "3" } },
];
export const pin2 = [
  { tag: "path", attrs: { "d": "M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "10", "r": "3" } },
];
export const plus = [
  { tag: "path", attrs: { "d": "M5 12h14" } },
  { tag: "path", attrs: { "d": "M12 5v14" } },
];
export const qr = [
  { tag: "rect", attrs: { "width": "5", "height": "5", "x": "3", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "5", "height": "5", "x": "16", "y": "3", "rx": "1" } },
  { tag: "rect", attrs: { "width": "5", "height": "5", "x": "3", "y": "16", "rx": "1" } },
  { tag: "path", attrs: { "d": "M21 16h-3a2 2 0 0 0-2 2v3" } },
  { tag: "path", attrs: { "d": "M21 21v.01" } },
  { tag: "path", attrs: { "d": "M12 7v3a2 2 0 0 1-2 2H7" } },
  { tag: "path", attrs: { "d": "M3 12h.01" } },
  { tag: "path", attrs: { "d": "M12 3h.01" } },
  { tag: "path", attrs: { "d": "M12 16v.01" } },
  { tag: "path", attrs: { "d": "M16 12h1" } },
  { tag: "path", attrs: { "d": "M21 12v.01" } },
  { tag: "path", attrs: { "d": "M12 21v-1" } },
];
export const refresh = [
  { tag: "path", attrs: { "d": "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" } },
  { tag: "path", attrs: { "d": "M21 3v5h-5" } },
  { tag: "path", attrs: { "d": "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" } },
  { tag: "path", attrs: { "d": "M8 16H3v5" } },
];
export const refresh2 = [
  { tag: "path", attrs: { "d": "M21 12a9 9 0 1 1-3-6.7L21 8" } },
  { tag: "path", attrs: { "d": "M21 3v5h-5" } },
];
export const rotateCw = [
  { tag: "path", attrs: { "d": "M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" } },
  { tag: "path", attrs: { "d": "M21 3v5h-5" } },
];
export const route = [
  { tag: "circle", attrs: { "cx": "6", "cy": "19", "r": "3" } },
  { tag: "path", attrs: { "d": "M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" } },
  { tag: "circle", attrs: { "cx": "18", "cy": "5", "r": "3" } },
];
export const scale = [
  { tag: "path", attrs: { "d": "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" } },
  { tag: "path", attrs: { "d": "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" } },
  { tag: "path", attrs: { "d": "M7 21h10" } },
  { tag: "path", attrs: { "d": "M12 3v18" } },
  { tag: "path", attrs: { "d": "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" } },
];
export const search = [
  { tag: "path", attrs: { "d": "m21 21-4.34-4.34" } },
  { tag: "circle", attrs: { "cx": "11", "cy": "11", "r": "8" } },
];
export const send = [
  { tag: "path", attrs: { "d": "M22 2 11 13" } },
  { tag: "path", attrs: { "d": "M22 2 15 22l-4-9-9-4Z" } },
];
export const send2 = [
  { tag: "path", attrs: { "d": "M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" } },
  { tag: "path", attrs: { "d": "m21.854 2.147-10.94 10.939" } },
];
export const settings = [
  { tag: "path", attrs: { "d": "M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "12", "r": "3" } },
];
export const shield = [
  { tag: "path", attrs: { "d": "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" } },
  { tag: "path", attrs: { "d": "m9 12 2 2 4-4" } },
];
export const shield2 = [
  { tag: "path", attrs: { "d": "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" } },
];
export const shieldAlert = [
  { tag: "path", attrs: { "d": "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" } },
  { tag: "path", attrs: { "d": "M12 8v4" } },
  { tag: "path", attrs: { "d": "M12 16h.01" } },
];
export const sparkles = [
  { tag: "path", attrs: { "d": "M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" } },
  { tag: "path", attrs: { "d": "M20 3v4" } },
  { tag: "path", attrs: { "d": "M22 5h-4" } },
  { tag: "path", attrs: { "d": "M4 17v2" } },
  { tag: "path", attrs: { "d": "M5 18H3" } },
];
export const triangleAlert = [
  { tag: "path", attrs: { "d": "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" } },
  { tag: "path", attrs: { "d": "M12 9v4" } },
  { tag: "path", attrs: { "d": "M12 17h.01" } },
];
export const truck = [
  { tag: "path", attrs: { "d": "M5 18H3c-.6 0-1-.4-1-1V7c0-.6.4-1 1-1h10c.6 0 1 .4 1 1v11" } },
  { tag: "path", attrs: { "d": "M14 9h4l4 4v4c0 .6-.4 1-1 1h-2" } },
  { tag: "circle", attrs: { "cx": "7", "cy": "18", "r": "2" } },
  { tag: "circle", attrs: { "cx": "17", "cy": "18", "r": "2" } },
];
export const user = [
  { tag: "path", attrs: { "d": "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" } },
  { tag: "circle", attrs: { "cx": "12", "cy": "7", "r": "4" } },
];
export const wrench = [
  { tag: "path", attrs: { "d": "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z" } },
];
export const x = [
  { tag: "path", attrs: { "d": "M18 6 6 18" } },
  { tag: "path", attrs: { "d": "m6 6 12 12" } },
];
