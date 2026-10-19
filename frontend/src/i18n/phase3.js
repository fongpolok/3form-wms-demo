// Phase 3 wording (APS planner + calendar).
export default {
  en: {
    nav: { plan: 'Plan (APS)', calendar: 'Calendar' },
    plan: {
      subtitle: 'The schedule for every workstation. Drafts wait for the Engineering Manager; urgent orders publish at once.',
      replan: 'Re-plan now', draftReady: 'New draft ready. Check what changed, then accept or reject.',
      accepted: 'Plan accepted and published. Workstation queues now follow it.', rejected: 'Draft rejected. The current plan stays.',
      draftTitle: 'Draft plan waiting for approval', moved: '{n} operation(s) moved', view: 'Show', current: 'Current plan', draft: 'Draft',
      accept: 'Accept', reject: 'Reject', noChange: 'No order finishes noticeably earlier or later.',
      change: { later: 'Later', earlier: 'Earlier', new: 'New' }, publishedBy: 'Published by {who} · {when}', window: 'Time window',
      days: 'days', weeks: 'wk', none: 'No plan yet. Press “Re-plan now”.', orders: 'Orders', finish: 'Planned finish',
      slack: 'Spare time', lateRisk: 'LATE RISK', beyond: 'Beyond 14 days', onTime: 'On time', blocked: 'Waiting for material (not planned)',
      plannedStart: 'planned', nDays: '{n} day | {n} days', nWeeks: '{n} wk', holidayToday: 'Today is a holiday: {name}. The plan starts on the next working day.',
    },
    calendar: {
      subtitle: 'Shifts, breaks, holidays and staffing used by the planner. Changes apply from the next re-plan.',
      readOnly: 'Only the PIC can change the calendar.', saved: 'Saved. Re-plan to use it.', shifts: 'Shifts', code: 'Shift',
      start: 'Start', end: 'End', break: 'Break', breakMin: 'Break (min)', workers: 'Workers', workingDays: 'Working days',
      day: { mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun' },
      holidays: 'Holidays', date: 'Date', name: 'Name', add: 'Add', staffing: 'Staffing changes',
      staffingHelp: 'Fewer (or more) people on a given shift. The planner leaves stations idle if people are short.',
      people: 'people', rules: 'Planning rules (settings.yaml)',
      rulesText: 'Plans {horizon_days} days ahead · {changeover_minutes} min changeover when the product changes · next {frozen_hours} h frozen · LATE RISK if within {late_buffer_hours} h of the due date · {workers_per_station} worker per running station.',
    },
    lean: { plannedH: 'Planned h', idleH: 'Idle h' },
    alerts: { kind: { PLAN_DRAFT: 'Plan draft', PLAN_CHANGED: 'Plan changed' } },
  },
  'zh-hant': {
    nav: { plan: '生產排程 (APS)', calendar: '工作日曆' },
    plan: {
      subtitle: '每個工作站的排程。草稿需工程經理批准;特急單會立即發佈。', replan: '立即重新排程',
      draftReady: '新草稿已完成。請查看改動,然後接受或拒絕。', accepted: '排程已接受並發佈,工作站隊列現跟隨排程。', rejected: '已拒絕草稿,維持現有排程。',
      draftTitle: '草稿排程等待批准', moved: '{n} 項工序有移動', view: '顯示', current: '現行排程', draft: '草稿', accept: '接受', reject: '拒絕',
      noChange: '沒有工單明顯提早或延遲。', change: { later: '延遲', earlier: '提早', new: '新' }, publishedBy: '由 {who} 發佈 · {when}',
      window: '時間範圍', days: '日', weeks: '週', none: '暫無排程,請按「立即重新排程」。', orders: '工單', finish: '預計完成', slack: '剩餘時間',
      lateRisk: '可能延誤', beyond: '超出 14 日', onTime: '準時', blocked: '等待物料(未排程)', plannedStart: '計劃', nDays: '{n} 日', nWeeks: '{n} 週', holidayToday: '今日為假期:{name}。排程由下一個工作日開始。',
    },
    calendar: {
      subtitle: '排程所用的班次、休息、假期及人手。下次重新排程時生效。', readOnly: '只有負責人可以修改日曆。', saved: '已儲存,重新排程後生效。',
      shifts: '班次', code: '班次', start: '開始', end: '結束', break: '休息', breakMin: '休息(分鐘)', workers: '人數', workingDays: '工作日',
      day: { mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日' }, holidays: '假期', date: '日期', name: '名稱', add: '新增',
      staffing: '人手變動', staffingHelp: '某班次人手較少(或較多)。人手不足時,排程會讓部分工作站停用。', people: '人', rules: '排程規則(settings.yaml)',
      rulesText: '排程 {horizon_days} 日 · 轉換產品需 {changeover_minutes} 分鐘 · 未來 {frozen_hours} 小時凍結 · 距到期日少於 {late_buffer_hours} 小時即標示可能延誤 · 每個運作中工作站需 {workers_per_station} 人。',
    },
    lean: { plannedH: '計劃小時', idleH: '閒置小時' },
    alerts: { kind: { PLAN_DRAFT: '排程草稿', PLAN_CHANGED: '排程已更改' } },
  },
}
