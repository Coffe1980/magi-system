"""
╔══════════════════════════════════════════════════════════════╗
║  MAGI SKILL — GERADOR VISUAL NERV                            ║
║  Carregado sob demanda pelo comando: visual <descrição>      ║
╚══════════════════════════════════════════════════════════════╝
"""

import re, webbrowser
from pathlib import Path
from colorama import Fore


def executar_visual(magi, descricao: str):
    """Ponto de entrada. Recebe instância MAGISystem e chama implementação."""
    _visual_impl(magi, descricao)


def _visual_impl(self, descricao: str):
    """Implementação completa do visual(). self = instância MAGISystem."""
    if not descricao:
        print(f"{Fore.YELLOW}  Uso: visual <descrição clara>")
        return

    from MagiSystem import MAGIInterface
    MAGIInterface.separador("MODO VISUAL — NERV PROTOCOL v2", Fore.MAGENTA)
    print(f"{Fore.WHITE}  Gerando: {Fore.YELLOW}{descricao}\n")

    system_prompt = (
        "Você é um engenheiro frontend especializado em interfaces NERV (Neon Genesis Evangelion) de alta qualidade.\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Retorne SOMENTE o código HTML completo e funcional.\n"
        "2. Não explique nada, não coloque ```html, apenas o código cru.\n"
        "3. O HTML deve começar com <!DOCTYPE html> e terminar com </html>.\n"
        "4. Use CSS moderno, scanlines, neon (laranja #FF6600 e ciano), glitch effects e animações.\n"
        "5. Faça um design limpo, cinematográfico e imersivo.\n"
        "6. Não repita estilos desnecessariamente.\n"
        "7. Mantenha o código organizado e completo.\n"
    )

    prompt = f"""Crie um dashboard completo no estilo NERV sobre: {descricao}

Requisitos:
- Fundo escuro com scanlines CRT
- Logo NERV com efeito neon/glitch
- Cards com informações de EVA Units, MAGI System e alertas
- Terminal com logs animados
- Paleta: preto, laranja #FF6600, vermelho, ciano
- Efeitos hover e animações suaves"""

    print(f"{Fore.MAGENTA}[VISUAL] Gerando código...\n")

    html = self._chamar_local(system_prompt, prompt)

    if not html:
        print(f"{Fore.YELLOW}  Local sem resposta — tentando cloud...")
        html = self._chamar_openai("gpt-4o-mini", system_prompt, prompt)
    if not html:
        print(f"{Fore.RED}  Nenhum modelo disponível para gerar o visual.")
        return

    html = html.strip()
    if not html.startswith("<!DOCTYPE"):
        match = re.search(r'<!DOCTYPE.*?</html>', html, re.DOTALL | re.IGNORECASE)
        html = match.group(0) if match else html

    nome_limpo  = re.sub(r'[^a-zA-Z0-9_-]', '_', descricao[:45]).strip('_')
    nome_arquivo = f"NERV_{nome_limpo}.html"
    caminho     = Path(__file__).parent / nome_arquivo

    caminho.write_text(html, encoding="utf-8")
    print(f"{Fore.GREEN}  [✓] Arquivo salvo: {nome_arquivo}")
    print(f"{Fore.CYAN}  Caminho: {caminho.resolve()}")

    try:
        webbrowser.open(f"file:///{caminho.resolve()}")
    except Exception:
        pass

    MAGIInterface.separador(cor=Fore.MAGENTA)
