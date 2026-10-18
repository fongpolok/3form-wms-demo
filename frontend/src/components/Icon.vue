<script setup>
// One small, consistent line-icon set (24px grid, 2px stroke). Decorative by
// default; pass `label` when the icon is the only thing explaining a control.
defineProps({ name: { type: String, required: true }, size: { type: Number, default: 22 }, label: String })
const paths = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  alert: 'M12 4l9 16H3L12 4zM12 10v4M12 17.5v.5',
  x: 'M6 6l12 12M18 6L6 18',
  play: 'M8 5l11 7-11 7V5z',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  pause: 'M8 5v14M16 5v14',
  gauge: 'M4 16a8 8 0 1116 0M12 16l4-5',
  scan: 'M4 8V5h3M17 5h3v3M20 16v3h-3M7 19H4v-3M7 12h10',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  station: 'M3 20h18M5 20V9l7-5 7 5v11M9 20v-6h6v6',
  list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  box: 'M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7M12 11v10',
  download: 'M12 4v11M7 10l5 5 5-5M4 20h16',
  people: 'M9 11a4 4 0 100-8 4 4 0 000 8zM2 21a7 7 0 0114 0M17 11a3 3 0 100-6M22 21a6 6 0 00-5-6',
  tablet: 'M6 2h12a1 1 0 011 1v18a1 1 0 01-1 1H6a1 1 0 01-1-1V3a1 1 0 011-1zM11 18h2',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z',
  gear: 'M12 15a3 3 0 100-6 3 3 0 000 6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1',
  wifi: 'M2 9a15 15 0 0120 0M5 12.5a10 10 0 0114 0M8.5 16a5 5 0 017 0M12 19.5v.01',
  out: 'M15 4h4a1 1 0 011 1v14a1 1 0 01-1 1h-4M10 17l5-5-5-5M15 12H3',
  ruler: 'M3 17L17 3l4 4L7 21l-4-4zM7 13l2 2M10 10l2 2M13 7l2 2',
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" :aria-hidden="label ? undefined : 'true'"
       :role="label ? 'img' : undefined" :aria-label="label">
    <path :d="paths[name]" />
  </svg>
</template>
