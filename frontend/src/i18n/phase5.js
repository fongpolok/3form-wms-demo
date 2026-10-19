// Phase 5 wording: ERP inbox / outbox.
export default {
  en: {
    nav: { erpInbox: 'ERP Inbox' },
    erp: {
      subtitle: 'Orders from SAP / Oracle that need a decision, and results waiting to go back to the ERP.', syncNow: 'Sync now',
      empty: 'Nothing waiting. Valid ERP orders become work orders by themselves.', approve: 'Fix and import', reject: 'Reject',
      imported: 'Imported as {wo}.', rejectedMsg: 'Rejected. It will not be imported again.', synced: 'Sync finished ({n} step(s)).',
      outbox: 'Results to the ERP (outbox)', good: 'Good', scrap: 'Scrap', detail: 'Detail', status: { pending: 'Waiting', sent: 'Sent' },
    },
    integrations: { erpHelp: 'SAP / Oracle send released orders in and get results back; Workday provides the staff list. Use Test to check the sign-in; orders are pulled every 15 minutes.' },
  },
  'zh-hant': {
    nav: { erpInbox: 'ERP 收件匣' },
    erp: {
      subtitle: '來自 SAP / Oracle、需要決定的工單,以及等待回傳 ERP 的結果。', syncNow: '立即同步', empty: '沒有待處理項目。有效的 ERP 工單會自動建立。',
      approve: '修正並匯入', reject: '拒絕', imported: '已匯入為 {wo}。', rejectedMsg: '已拒絕,不會再次匯入。', synced: '同步完成({n} 步)。',
      outbox: '回傳 ERP 的結果(寄件匣)', good: '良品', scrap: '報廢', detail: '詳情', status: { pending: '等待中', sent: '已傳送' },
    },
    integrations: { erpHelp: 'SAP / Oracle 傳入已放行工單並接收結果;Workday 提供員工名單。按「測試」檢查登入;每 15 分鐘拉取工單。' },
  },
}
