import test from 'node:test';
import assert from 'node:assert/strict';
import {addTask,editTask,toggleTask,filterTasks,cleanTitle,createTaskIdGenerator} from '../lib/tasks.ts';
test('add trims title, creates active item and preserves input',()=>{const before=[];const after=addTask(before,'  Проверить идею  ','1');assert.deepEqual(after,[{id:'1',title:'Проверить идею',done:false}]);assert.deepEqual(before,[]);});
test('empty and whitespace titles rejected',()=>{for(const title of ['', '   ', '\n\t'])assert.throws(()=>cleanTitle(title));});
test('160-character boundary',()=>{assert.equal(cleanTitle('я'.repeat(160)).length,160);assert.throws(()=>cleanTitle('я'.repeat(161)));});
test('duplicate IDs rejected',()=>{assert.throws(()=>addTask(addTask([],'A','1'),'B','1'));});
test('editing preserves identity and completion',()=>{const before=[{id:'1',title:'A',done:true},{id:'2',title:'B',done:false}];const after=editTask(before,'1',' C ');assert.deepEqual(after,[{id:'1',title:'C',done:true},before[1]]);assert.equal(before[0].title,'A');});
test('invalid edit leaves original unchanged',()=>{const before=addTask([],'A','1');assert.throws(()=>editTask(before,'1',' '));assert.equal(before[0].title,'A');});
test('completion is reversible and immutable',()=>{const before=addTask([],'A','1');const done=toggleTask(before,'1');assert.equal(done[0].done,true);assert.equal(before[0].done,false);assert.deepEqual(toggleTask(done,'1'),before);});
test('all active and completed filters',()=>{const tasks=[{id:'1',title:'A',done:false},{id:'2',title:'B',done:true}];assert.deepEqual(filterTasks(tasks,'all'),tasks);assert.deepEqual(filterTasks(tasks,'active'),[tasks[0]]);assert.deepEqual(filterTasks(tasks,'done'),[tasks[1]]);assert.deepEqual(filterTasks([],'done'),[]);});
test('HTML-like task titles remain plain data',()=>{assert.equal(addTask([],'<img src=x onerror=alert(1)>','1')[0].title,'<img src=x onerror=alert(1)>');});

test('ID generator works without secure-context crypto and produces unique IDs',()=>{const next=createTaskIdGenerator();const ids=Array.from({length:1000},next);assert.equal(new Set(ids).size,1000);assert.equal(ids[0],'task-1');});
