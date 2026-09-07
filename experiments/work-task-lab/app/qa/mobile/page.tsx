import { notFound } from 'next/navigation';
export default function MobileQA() {
  if (process.env.NODE_ENV !== 'development') notFound();
  return <main style={{padding:20}}><h1 style={{fontSize:20,marginBottom:16}}>Mobile QA · 390 × 844 CSS px</h1><iframe title="Мобильный интерфейс" src="/" width="390" height="844" style={{border:'0',outline:'1px solid #b9c4da',display:'block'}}/></main>;
}
