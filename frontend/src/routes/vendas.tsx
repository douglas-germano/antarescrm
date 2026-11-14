import { useState } from 'react';
import { createFileRoute, Link } from '@tanstack/react-router';
import { ArrowDown, ArrowRight, Bot, CalendarCheck, Check, FileInput, Instagram, Kanban, MessagesSquare, Plug, Workflow, BarChart3, Mail } from 'lucide-react';
import '@fontsource/manrope/700.css';
import '@fontsource/manrope/800.css';
import '@/styles/sales.css';

export const Route = createFileRoute('/vendas')({
  head: () => ({ meta: [
    { title: 'Antares CRM | Toda venda tem um próximo passo' },
    { name: 'description', content: 'Organize conversas de WhatsApp e Instagram, negociações e follow-ups no Antares CRM.' },
  ] }),
  component: SalesPage,
});

const stages = [
  {
    title: 'Conversa',
    icon: MessagesSquare,
    label: 'WhatsApp · Pedido de orçamento',
    detail: 'Pode me mandar a proposta hoje? A gente consegue decidir na sexta.',
    action: 'Consulte o histórico da conversa antes de enviar a proposta.',
  },
  {
    title: 'Proposta',
    icon: Kanban,
    label: 'Funil · Proposta enviada',
    detail: 'Projeto de móveis sob medida',
    action: 'Registre a oportunidade no funil para a equipe ver em que etapa ela está.',
  },
  {
    title: 'Retorno',
    icon: CalendarCheck,
    label: 'Tarefas · Sexta, 10h',
    detail: 'Retomar a proposta com o cliente',
    action: 'Crie uma tarefa de follow-up para voltar à conversa na sexta.',
  },
];

const modules = [
  { icon: MessagesSquare, title: 'Caixa de entrada única', text: 'WhatsApp e Instagram na mesma tela, com responsável por conversa, painel do contato e o histórico ao lado.' },
  { icon: Kanban, title: 'Funil de vendas', text: 'Arraste cada negócio entre as etapas e veja o que está parado. Contatos e empresas ficam ligados à oportunidade.' },
  { icon: Workflow, title: 'Automações com Se / Senão', text: 'Monte fluxos visuais: ao receber um formulário ou um novo contato, crie tarefa, envie mensagem e siga um caminho conforme a resposta.' },
  { icon: Bot, title: 'Atlas, o assistente de conversas', text: 'Atribua uma conversa ao Atlas para responder mensagens de texto e áudio. Pause quando quiser assumir o atendimento.' },
  { icon: FileInput, title: 'Formulários e páginas de captura', text: 'Crie formulários e funis de páginas com seu domínio. Cada envio vira contato e negócio no funil.' },
  { icon: CalendarCheck, title: 'Tarefas e agenda', text: 'Distribua follow-ups, marque datas e deixe clientes reservarem horário por um link de agendamento.' },
  { icon: Instagram, title: 'Instagram completo', text: 'Várias contas, publicação e agendamento de posts, métricas e respostas a comentários.' },
  { icon: Mail, title: 'Campanhas', text: 'Envie e-mails para listas de contatos a partir de modelos salvos.' },
  { icon: BarChart3, title: 'Relatórios', text: 'Vendas por responsável, perdas e atividades da equipe, para saber onde a operação trava.' },
  { icon: Plug, title: 'Conecte sua IA (MCP)', text: 'Libere o Claude, o Cursor e outros agentes para ler conversas e responder, com permissões por token e confirmação antes de qualquer envio.' },
];

const steps = [
  { title: 'Receba o convite', text: 'O administrador cria a conta da sua empresa. Cada pessoa da equipe entra por convite, por e-mail.' },
  { title: 'Conecte os canais', text: 'Leia o QR Code para o WhatsApp e autorize o Instagram em Configurações. As conversas passam a chegar à caixa de entrada.' },
  { title: 'Monte o funil e as tarefas', text: 'Defina as etapas, crie as primeiras oportunidades e agende o retorno de cada uma.' },
];

const pains = [
  'Proposta enviada, retorno esquecido.',
  'Cliente chama no Instagram e no WhatsApp e ninguém liga as pontas.',
  'Conversa importante some no meio de outras mensagens.',
  'O dono pergunta "como está a venda?" e a resposta está na cabeça de alguém.',
];

const faq = [
  { question: 'Funciona com WhatsApp e Instagram?', answer: 'Sim. O WhatsApp é conectado por QR Code em Configurações e o Instagram pela autorização da sua conta profissional. Ambos aparecem na mesma caixa de entrada.' },
  { question: 'Posso conectar mais de uma conta de Instagram?', answer: 'Sim. O Antares aceita várias contas, com publicação, métricas e comentários de cada uma.' },
  { question: 'O Atlas responde por conta própria?', answer: 'Só nas conversas que você atribuir a ele. Para assumir o atendimento, basta pausá-lo na conversa.' },
  { question: 'Como começo a usar?', answer: 'O acesso é por convite. Quando a conta é criada, a equipe recebe um e-mail para definir a senha e entrar.' },
  { question: 'O preço é por usuário?', answer: 'A assinatura é de R$ 197 por mês por conta (workspace).' },
  { question: 'Quando vence a primeira cobrança?', answer: 'Para novas contas em teste, a primeira fatura da assinatura vence ao fim do período de 14 dias.' },
  { question: 'Como pago a assinatura?', answer: 'O responsável pela conta entra no Antares e gera uma fatura. O pagamento é feito no Asaas com Pix, boleto ou cartão, conforme as opções da fatura.' },
];

function AccessLink() {
  return <Link to="/cadastro" className="sales-button">Como obter acesso <ArrowRight size={18} /></Link>;
}

function SalesDemo() {
  const [selected, setSelected] = useState(0);
  const { icon: Icon, label, detail, action } = stages[selected];
  return (
    <figure className="sales-demo">
      <figcaption>Exemplo interativo · Dados ilustrativos</figcaption>
      <div className="sales-demo-controls" role="group" aria-label="Etapas do exemplo">
        {stages.map(({ title }, index) => (
          <button key={title} type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}>{title}</button>
        ))}
      </div>
      <div className="sales-demo-panel" aria-live="polite">
        <span className="sales-demo-icon"><Icon size={24} aria-hidden="true" /></span>
        <small>{label}</small>
        <strong>{detail}</strong>
        <p>{action}</p>
      </div>
    </figure>
  );
}

function SalesPage() {
  return (
    <div className="sales-page">
      <header className="sales-header sales-wrap">
        <Link to="/vendas" className="sales-brand"><img src="/mark.svg" alt="" width="32" height="32" />Antares CRM</Link>
        <nav aria-label="Navegação da página">
          <a href="#recursos">Recursos</a>
          <a href="#plano">Plano</a>
          <Link to="/login">Entrar <ArrowRight size={16} /></Link>
        </nav>
      </header>
      <main>
        <section className="sales-hero sales-wrap" aria-labelledby="sales-title">
          <div className="sales-intro">
            <h1 id="sales-title">Saiba com quem falar <em>e quando voltar.</em></h1>
            <p>O Antares é o CRM para equipes que vendem pelo WhatsApp e pelo Instagram. Reúna conversas, propostas e tarefas de retorno em um só lugar.</p>
            <div className="sales-actions"><AccessLink /><a href="#como-funciona">Veja como funciona <ArrowDown size={17} /></a></div>
            <small className="sales-trial">14 dias de teste para novas contas convidadas</small>
          </div>
          <SalesDemo />
        </section>

        <section className="sales-pains sales-wrap" aria-labelledby="sales-pains-title">
          <h2 id="sales-pains-title">Você reconhece alguma destas cenas?</h2>
          <ul>{pains.map(item => <li key={item}>{item}</li>)}</ul>
        </section>

        <section id="como-funciona" className="sales-story">
          <div className="sales-wrap sales-story-grid">
            <h2>A proposta saiu na terça. Quem retoma na sexta?</h2>
            <div>
              <p>O cliente pediu um orçamento pelo WhatsApp. Sua equipe enviou a proposta e combinou de voltar a falar na sexta. Até lá, chegaram outras mensagens e a conversa desceu na lista.</p>
              <p>No Antares, quem enviou a proposta registra a etapa no funil e cria uma tarefa para sexta. Quando chega a hora do retorno, o responsável abre o histórico e segue de onde a equipe parou.</p>
            </div>
          </div>
        </section>

        <section className="sales-features sales-wrap" aria-labelledby="sales-features">
          <h2 id="sales-features">O que sua equipe consegue acompanhar</h2>
          <div className="sales-feature-grid">
            <article><MessagesSquare size={24} aria-hidden="true" /><h3>O que o cliente já pediu</h3><p>Consulte as conversas do WhatsApp e do Instagram na caixa de entrada.</p></article>
            <article><Kanban size={24} aria-hidden="true" /><h3>Em que etapa está a venda</h3><p>Veja quais negócios precisam de proposta, estão em negociação ou já foram fechados.</p></article>
            <article><CalendarCheck size={24} aria-hidden="true" /><h3>Quem precisa de retorno</h3><p>Distribua tarefas e combine datas de follow-up para a equipe.</p></article>
          </div>
        </section>

        <section id="recursos" className="sales-modules sales-wrap" aria-labelledby="sales-modules-title">
          <h2 id="sales-modules-title">Tudo o que a venda pede, no mesmo lugar</h2>
          <div className="sales-module-grid">
            {modules.map(({ icon: Icon, title, text }) => <article key={title}><Icon size={22} aria-hidden="true" /><h3>{title}</h3><p>{text}</p></article>)}
          </div>
        </section>

        <section className="sales-steps sales-wrap" aria-labelledby="sales-steps-title">
          <h2 id="sales-steps-title">Do convite ao primeiro retorno agendado</h2>
          <ol>{steps.map(({ title, text }) => <li key={title}><h3>{title}</h3><p>{text}</p></li>)}</ol>
        </section>

        <section id="plano" className="sales-plan" aria-labelledby="sales-plan-title">
          <div className="sales-wrap sales-plan-grid">
            <div>
              <h2 id="sales-plan-title">Assinatura Antares CRM</h2>
              <ul>{['Caixa de entrada de WhatsApp e Instagram', 'Funil, contatos e histórico de oportunidades', 'Tarefas, agenda e automações', 'Formulários, páginas de captura e campanhas', 'Atlas, Instagram completo e acesso por MCP', 'Toda a equipe na mesma conta, sem cobrança por usuário'].map(item => <li key={item}><Check size={18} aria-hidden="true" />{item}</li>)}</ul>
            </div>
            <div className="sales-offer">
              <p className="sales-price"><strong>R$ 197</strong> <span>/ mês por conta</span></p>
              <p>14 dias de teste para novas contas convidadas.</p>
              <AccessLink />
              <Link to="/assinatura" className="sales-pay-link">Já tenho conta. Abrir assinatura <ArrowRight size={17} /></Link>
            </div>
          </div>
        </section>

        <section className="sales-faq sales-wrap" aria-labelledby="sales-faq-title">
          <h2 id="sales-faq-title">Perguntas frequentes</h2>
          <div>{faq.map(({ question, answer }) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div>
        </section>

        <section className="sales-close sales-wrap" aria-labelledby="sales-close-title">
          <h2 id="sales-close-title">Sua equipe sabe quais propostas retomar nesta semana?</h2>
          <div className="sales-actions"><AccessLink /><a href="mailto:contato@douglasgermano.com?subject=Acesso%20ao%20Antares%20CRM">Falar com a gente <ArrowRight size={17} /></a></div>
        </section>
      </main>
      <footer className="sales-footer sales-wrap"><span>Antares CRM</span><Link to="/login">Entrar na conta <ArrowRight size={16} /></Link></footer>
    </div>
  );
}
