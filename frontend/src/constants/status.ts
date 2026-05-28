export const STRATEGY_STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '活跃' },
  archived: { color: 'orange', label: '已归档' },
  deleted: { color: 'red', label: '已删除' },
  draft: { color: 'blue', label: '草稿' },
};

export const BACKTEST_STATUS_MAP: Record<string, { color: string; label: string }> = {
  pending: { color: 'orange', label: '待运行' },
  running: { color: 'blue', label: '运行中' },
  completed: { color: 'green', label: '已完成' },
  failed: { color: 'red', label: '失败' },
};
