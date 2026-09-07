'use client';
import { useRef, useState } from 'react';
import { Plus, Pencil, Check, ListTodo, ArrowUpRight } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { addTask, editTask, toggleTask, filterTasks, createTaskIdGenerator, type Task, type Filter } from '@/lib/tasks';

export default function Home() {
  const [nextId] = useState(createTaskIdGenerator);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [editError, setEditError] = useState('');
  const [notice, setNotice] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const completed = tasks.filter(t => t.done).length;
  const visible = filterTasks(tasks, filter);
  function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      const updated = addTask(tasks, title, nextId());
      setTasks(updated); setTitle(''); setError(''); setFilter('all');
      setNotice('Задача добавлена.'); input.current?.focus();
    } catch (err) { setError((err as Error).message); }
  }
  function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      setTasks(editTask(tasks, editing!, draft)); setEditing(null); setEditError('');
      setNotice('Изменения сохранены.');
    } catch (err) { setEditError((err as Error).message); }
  }
  function changeFilter(value: string) { setFilter(value as Filter); setEditing(null); setEditError(''); }
  return <main className="workspace">
    <header className="topbar"><a href="/" className="brand" aria-label="VIREN Задачи"><span className="brandmark"><Check size={20}/></span>VIREN<span className="brand-divider">/</span><span className="brand-sub">Задачи</span></a><span className="edition">ЛИЧНОЕ ПРОСТРАНСТВО</span></header>
    <section className="board" aria-labelledby="heading">
      <div className="intro"><div><p className="eyebrow">МЕНЬШЕ ШУМА. БОЛЬШЕ ДЕЛА.</p><h1 id="heading">Один шаг за раз<span>.</span></h1><p className="subtitle">Всё, что хочешь сделать, — здесь.</p></div><div className="total"><strong>{tasks.length.toString().padStart(2,'0')}</strong><span>в списке</span></div></div>
      <div className="task-panel">
        <form onSubmit={add} className="add-form" noValidate><label htmlFor="new-task">Что нужно сделать?</label><div className="add-controls"><input ref={input} id="new-task" value={title} onChange={e => {setTitle(e.target.value); setError('');}} placeholder="Например, проверить новую идею" maxLength={160} aria-invalid={!!error} aria-describedby={error ? 'add-error' : undefined}/><button className="primary" type="submit"><Plus size={19}/><span>Добавить</span></button></div>{error && <p id="add-error" role="alert" className="error">{error}</p>}</form>
        <Tabs value={filter} onValueChange={changeFilter} className="task-tabs"><div className="toolbar"><TabsList aria-label="Фильтр задач" className="filters"><TabsTrigger value="all">Все <span>{tasks.length}</span></TabsTrigger><TabsTrigger value="active">В работе <span>{tasks.length-completed}</span></TabsTrigger><TabsTrigger value="done">Готово <span>{completed}</span></TabsTrigger></TabsList><span className="progress-text">{completed} из {tasks.length} выполнено</span></div>
          <TabsContent value={filter} className="list-panel">
            {visible.length === 0 ? <div className="empty"><span className="empty-icon"><ListTodo size={30}/></span><h2>{filter === 'done' ? 'Первые победы впереди' : filter === 'active' && tasks.length ? 'Всё сделано!' : 'Место для твоих планов'}</h2><p>{filter === 'done' ? 'Завершённые задачи появятся здесь.' : filter === 'active' && tasks.length ? 'Можно выдохнуть или придумать что-то новое.' : 'Добавь первую задачу и начни с малого.'}</p></div> : <ul className="task-list">{visible.map(task => <li key={task.id} className={'task-row'+(task.done ? ' completed' : '')} data-task-id={task.id}>
              <Checkbox className="task-check" checked={task.done} onCheckedChange={() => {setTasks(toggleTask(tasks,task.id)); setNotice(task.done ? 'Задача возвращена в работу.' : 'Задача завершена.');}} aria-label={(task.done ? 'Вернуть в работу: ' : 'Завершить: ')+task.title}/>
              {editing === task.id ? <form className="edit-form" onSubmit={save}><label className="sr-only" htmlFor={'edit-'+task.id}>Новое название</label><input autoFocus id={'edit-'+task.id} value={draft} onChange={e=>{setDraft(e.target.value);setEditError('');}} maxLength={160} onKeyDown={e=>{if(e.key==='Escape'){setEditing(null);setEditError('');}}} aria-invalid={!!editError} aria-describedby={editError ? 'edit-error' : undefined}/><div className="edit-actions"><button className="save" type="submit">Сохранить</button><button className="cancel" type="button" onClick={()=>{setEditing(null);setEditError('');}}>Отмена</button></div>{editError && <p className="error" id="edit-error" role="alert">{editError}</p>}</form> : <><span className="task-title">{task.title}</span><button className="edit-button" type="button" aria-label={'Редактировать: '+task.title} onClick={()=>{setEditing(task.id);setDraft(task.title);setEditError('');}}><Pencil size={17}/></button></>}
            </li>)}</ul>}
          </TabsContent>
        </Tabs>
        <footer className="panel-footer"><span><span className="small-check">✓</span> Маленькие шаги тоже считаются</span><ArrowUpRight size={17}/></footer>
      </div>
      <p className="session-note">Тестовый список · задачи хранятся до обновления страницы</p>
      <p className="sr-only" role="status" aria-live="polite">{notice}</p>
    </section>
  </main>;
}
