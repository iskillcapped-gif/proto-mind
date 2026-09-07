export type Task = { id: string; title: string; done: boolean };
export type Filter = 'all' | 'active' | 'done';
export function cleanTitle(value: string): string {
  const title = value.trim();
  if (!title) throw new Error('Напиши название задачи.');
  if (title.length > 160) throw new Error('Не больше 160 символов.');
  return title;
}
export function addTask(tasks: Task[], title: string, id: string): Task[] {
  if (tasks.some(t => t.id === id)) throw new Error('Повторный идентификатор задачи.');
  return [...tasks, { id, title: cleanTitle(title), done: false }];
}
export function editTask(tasks: Task[], id: string, title: string): Task[] {
  const cleaned = cleanTitle(title);
  return tasks.map(t => t.id === id ? { ...t, title: cleaned } : t);
}
export function toggleTask(tasks: Task[], id: string): Task[] {
  return tasks.map(t => t.id === id ? { ...t, done: !t.done } : t);
}
export function filterTasks(tasks: Task[], filter: Filter): Task[] {
  return tasks.filter(t => filter === 'all' || (filter === 'done' ? t.done : !t.done));
}

// IDs only need to be unique within this in-memory list; works on HTTP too.
export function createTaskIdGenerator() {
  let sequence = 0;
  return () => `task-${++sequence}`;
}
