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
      short: 'Not enough stock', batch: 'Pick list', builtinWalk: 'Built-in route: {m} m', depot: 'Start and finish at aisle {aisle}, position {position}.',
    },
    bins: { aisle: 'Aisle', position: 'Position', location: 'Location', setLocation: 'Save location', noLocation: 'not set' },
    alerts: { kind: { OPTIMISER_UNAVAILABLE: 'cuOpt unavailable' } },
    changeover: {
      title: 'Saving changeovers',
      help: 'Changing product on a workstation costs cleaning and set-up time. These two settings decide how hard the planners try to avoid it.',
      cost: 'Changeover cost (cuOpt), minutes', costHint: 'One changeover counts like being this many minutes late. 0 = ignore.',
      group: 'Group same product (built-in), days', groupHint: 'Run the same product next if its due date is within this many days. Never ahead of urgent orders. 0 = off.',
    },
    compare: {
      title: 'Compare: Built-in vs NVIDIA cuOpt', help: 'Plans the same open orders with both engines, right now. Nothing is saved or changed.',
      run: 'Compare now', running: 'Planning with both engines (about 20 seconds)…',
      late_orders: 'Orders at risk of being late', hours_late: 'Total hours past target', changeovers: 'Product changeovers',
      changeover_minutes: 'Changeover time', all_done_by: 'Everything finished by',
      moved: 'Orders that finish at a different time ({n})', same: 'Both engines give every order the same finish time.',
      change: 'With cuOpt', earlier: 'earlier', later: 'later',
      howToUse: 'To use the cuOpt plan: choose cuOpt for the production plan in Settings → Integrations, then Re-plan now and Accept the draft.',
    },
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
      short: '庫存不足', batch: '揀貨單', builtinWalk: '內建路線:{m} 米', depot: '由通道 {aisle}、位置 {position} 出發並返回。',
    },
    bins: { aisle: '通道', position: '位置', location: '位置', setLocation: '儲存位置', noLocation: '未設定' },
    alerts: { kind: { OPTIMISER_UNAVAILABLE: 'cuOpt 無法使用' } },
    changeover: {
      title: '減少換線',
      help: '工作站轉換產品需要清潔及設定時間。這兩項設定決定排程引擎如何盡量避免換線。',
      cost: '換線成本(cuOpt),分鐘', costHint: '每次換線等同延誤這麼多分鐘。0 = 不計算。',
      group: '同產品合併(內建),日', groupHint: '如同一產品的到期日相差在此日數內,接著生產。不會排在緊急工單之前。0 = 關閉。',
    },
    compare: {
      title: '比較:內建 vs NVIDIA cuOpt', help: '用兩個引擎即時為同一批未完成工單排程,不會儲存或更改任何資料。',
      run: '立即比較', running: '兩個引擎排程中(約 20 秒)…',
      late_orders: '有延誤風險的工單', hours_late: '超出目標的總時數', changeovers: '產品換線次數',
      changeover_minutes: '換線時間', all_done_by: '全部完成時間',
      moved: '完成時間不同的工單({n})', same: '兩個引擎給所有工單的完成時間相同。',
      change: '使用 cuOpt', earlier: '提早', later: '延後',
      howToUse: '如要採用 cuOpt 排程:在「設定 → 系統整合」把生產排程設為 cuOpt,再按「立即重新排程」並接受草稿。',
    },
    plan: { engine: '排程引擎', engineBuiltin: '內建排程', engineCuopt: 'NVIDIA cuOpt' },
  },
}
