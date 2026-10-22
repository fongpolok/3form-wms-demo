// v3.6.0 wording: optional NVIDIA cuOpt for planning and pick routes, bin locations.
export default {
  en: {
    optimiser: {
      title: 'Optimiser (planning and pick routes)',
      help: 'Built-in needs nothing extra. NVIDIA cuOpt needs a cuOpt server on a computer with an NVIDIA GPU. If cuOpt is chosen and does not answer, nothing changes: the last plan stays and a red alert appears.',
      planEngine: 'Production plan', pickEngine: 'Pick routes', builtin: 'Built-in', cuopt: 'NVIDIA cuOpt',
      url: 'cuOpt server address', urlHint: 'e.g. http://10.0.0.5:5000', token: 'Access token (optional)',
      tokenSet: 'saved', noToken: 'none', clearToken: 'Remove token',
    },
    pick: {
      route: 'Plan pick route', title: 'Pick route', engine: 'Engine', distance: 'Walk', stop: 'Stop', bin: 'Bin',
      where: 'Aisle · position', items: 'Pick', unlocated: 'Not on the map (add aisle and position on the Bins page)',
      short: 'Not enough stock', batch: 'Pick list', depot: 'Start and finish at aisle {aisle}, position {position}.',
    },
    bins: { aisle: 'Aisle', position: 'Position', location: 'Location', setLocation: 'Save location', noLocation: 'not set' },
    alerts: { kind: { OPTIMISER_UNAVAILABLE: 'cuOpt unavailable' } },
    plan: { engine: 'Planned by', engineBuiltin: 'built-in planner', engineCuopt: 'NVIDIA cuOpt' },
  },
  'zh-hant': {
    optimiser: {
      title: '優化引擎(排程及揀貨路線)',
      help: '內建引擎無需額外設備。NVIDIA cuOpt 需要一部配備 NVIDIA GPU 的電腦運行 cuOpt 伺服器。如選用 cuOpt 而它沒有回應,系統不作任何改動:保留上一份排程,並發出紅色警報。',
      planEngine: '生產排程', pickEngine: '揀貨路線', builtin: '內建', cuopt: 'NVIDIA cuOpt',
      url: 'cuOpt 伺服器地址', urlHint: '例如 http://10.0.0.5:5000', token: '存取權杖(可選)',
      tokenSet: '已儲存', noToken: '沒有', clearToken: '移除權杖',
    },
    pick: {
      route: '規劃揀貨路線', title: '揀貨路線', engine: '引擎', distance: '步行', stop: '站', bin: '貨位',
      where: '通道 · 位置', items: '揀取', unlocated: '未在地圖上(請在「貨位」頁加入通道及位置)',
      short: '庫存不足', batch: '揀貨單', depot: '由通道 {aisle}、位置 {position} 出發並返回。',
    },
    bins: { aisle: '通道', position: '位置', location: '位置', setLocation: '儲存位置', noLocation: '未設定' },
    alerts: { kind: { OPTIMISER_UNAVAILABLE: 'cuOpt 無法使用' } },
    plan: { engine: '排程引擎', engineBuiltin: '內建排程', engineCuopt: 'NVIDIA cuOpt' },
  },
}
