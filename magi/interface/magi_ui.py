"""
magi/interface/magi_ui.py
Funções de UI/terminal extraídas de MAGIInterface.
Responsabilidade única: exibição no console.
"""
from colorama import Fore, Style


class MAGIInterface:
    """Helpers de formatação de terminal."""

    LARGURA = 70

    @staticmethod
    def separador(titulo: str = "", cor: str = Fore.RED) -> None:
        if titulo:
            pad = max(0, (MAGIInterface.LARGURA - len(titulo) - 2) // 2)
            linha = "─" * pad + f" {titulo} " + "─" * pad
        else:
            linha = "─" * MAGIInterface.LARGURA
        print(f"{cor}{linha}{Style.RESET_ALL}")

    @staticmethod
    def tag_intencao(intencao: str) -> None:
        cores = {
            "técnico":  Fore.CYAN,
            "ético":    Fore.GREEN,
            "criativo": Fore.MAGENTA,
            "factual":  Fore.YELLOW,
            "decisão":  Fore.WHITE,
            "conversa": Fore.WHITE,
        }
        cor = cores.get(intencao, Fore.WHITE)
        print(f"  {cor}[{intencao.upper()}]{Style.RESET_ALL}", end="")

    @staticmethod
    def banner(versao: str = "15.0") -> None:
        print(f"""
{Fore.RED}╔══════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}███╗   ███╗ █████╗  ██████╗ ██╗{Fore.RED}                               ║
║  {Fore.WHITE}████╗ ████║██╔══██╗██╔════╝ ██║{Fore.RED}                               ║
║  {Fore.WHITE}██╔████╔██║███████║██║  ███╗██║{Fore.RED}                               ║
║  {Fore.WHITE}██║╚██╔╝██║██╔══██║██║   ██║██║{Fore.RED}                               ║
║  {Fore.WHITE}██║ ╚═╝ ██║██║  ██║╚██████╔╝██║{Fore.RED}                               ║
║  {Fore.WHITE}╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝{Fore.RED}   v{versao}                  ║
║  {Fore.CYAN}SISTEMA CONSCIENTE — NERV HQ{Fore.RED}                                  ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
""")

    @staticmethod
    def painel_nucleos(nucleos_status: dict) -> None:
        """Exibe painel resumido dos núcleos."""
        from magi.core.magi_config import NUCLEOS
        print(f"\n{Fore.RED}  ╔═══ NÚCLEOS ATIVOS ════════════════════════════╗")
        for nome, cfg in NUCLEOS.items():
            status = nucleos_status.get(nome, "?")
            cor_status = Fore.GREEN if status == "ONLINE" else Fore.RED
            cor_nucleo = cfg.get("cor", Fore.WHITE)
            emoji = cfg.get("emoji", "·")
            print(f"  ║  {cor_nucleo}{nome:12}{Fore.WHITE} {emoji}  {cor_status}{status:7}{Fore.WHITE}  {cfg.get('subtitulo','')}")
        print(f"{Fore.RED}  ╚═══════════════════════════════════════════════╝{Style.RESET_ALL}\n")
