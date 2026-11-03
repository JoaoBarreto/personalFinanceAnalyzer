import { APP } from "../lib/about";
import Logo from "../components/Logo";

export default function About() {
  return (
    <>
      <div className="about-hero card">
        <Logo size={56} />
        <div>
          <h1>{APP.nome}</h1>
          <p className="muted">{APP.descricao}. Versão {APP.versao}.</p>
        </div>
      </div>
      <div className="grid2">
        <section className="card">
          <h2>O que faz</h2>
          <ol className="steps">
            <li><strong>Importa</strong> o extrato <code>.xls</code> do homebanking, validado ao pormenor: se o ficheiro não seguir o formato original, é recusado e explica porquê.</li>
            <li><strong>Categoriza</strong> os movimentos com regras que se aprendem consigo: categoriza-se uma vez e aplica-se a todo o histórico e aos extratos seguintes.</li>
            <li><strong>Analisa</strong> receitas, despesas, poupança e saldo por mês e por ano, e confirma que as contas fecham ao cêntimo.</li>
          </ol>
        </section>
        <section className="card">
          <h2>Privacidade e segurança</h2>
          <ul className="plain">
            <li>Os dados bancários ficam <strong>apenas neste servidor</strong>; nada é enviado a serviços externos.</li>
            <li>O acesso exige palavra-passe (guardada com hash argon2), sessão no servidor e proteção contra pedidos forjados.</li>
            <li>Os ficheiros importados não são guardados: apenas os movimentos extraídos.</li>
            <li>O acesso remoto faz-se por rede privada (Tailscale); o acesso na rede de casa é opcional.</li>
          </ul>
        </section>
      </div>
      <section className="card">
        <h2>Autor e tecnologia</h2>
        <p>Desenvolvida por <strong>{APP.autor}</strong> para uso doméstico, com o apoio do Claude (Anthropic).</p>
        <p className="muted small">Frontend React + TypeScript · Backend Python (FastAPI) · Base de dados PostgreSQL · Docker. Código em <a href={APP.repo} target="_blank" rel="noreferrer">GitHub</a>. © {APP.ano} {APP.autor}.</p>
      </section>
    </>
  );
}
