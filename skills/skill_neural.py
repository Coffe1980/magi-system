"""
╔══════════════════════════════════════════════════════════════╗
║  MAGI SKILL — MÓDULO NEURAL                                  ║
║  Carregado sob demanda pelos comandos:                       ║
║    neural treinar · neural status                            ║
╚══════════════════════════════════════════════════════════════╝
"""

import gzip, urllib.request
from pathlib import Path
import numpy as np
from colorama import Fore

class MAGINeural:
    """Rede neural MLP via sklearn. Treina no MNIST. Compatível com Python 3.14 (sem TensorFlow)."""
    MODEL_PATH = Path(__file__).parent / "magi_neural.pkl"

    def __init__(self):
        self._modelo = None
        self._treinado = False
        self._acuracia = None
        self._historico_treino = []

    def _construir_modelo(self):
        try:
            from sklearn.neural_network import MLPClassifier
            return MLPClassifier(
                hidden_layer_sizes=(256, 64),
                activation='relu',
                solver='adam',
                max_iter=1,          # iterações controladas manualmente por epoch
                warm_start=True,     # permite treino incremental
                random_state=42,
                verbose=False,
            )
        except ImportError:
            return None

    def _carregar_mnist(self):
        """Baixa e retorna MNIST via urllib (sem keras/tensorflow)."""
        import gzip, struct, urllib.request
        base = "https://storage.googleapis.com/cvdf-datasets/mnist/"
        arquivos = {
            "train_img": "train-images-idx3-ubyte.gz",
            "train_lbl": "train-labels-idx1-ubyte.gz",
            "test_img":  "t10k-images-idx3-ubyte.gz",
            "test_lbl":  "t10k-labels-idx1-ubyte.gz",
        }
        cache_dir = Path(__file__).parent / ".mnist_cache"
        cache_dir.mkdir(exist_ok=True)

        def _ler(nome, n_skip, fmt, count):
            local = cache_dir / nome
            if not local.exists():
                urllib.request.urlretrieve(base + nome, local)
            with gzip.open(local, 'rb') as f:
                f.read(n_skip)
                return np.frombuffer(f.read(), dtype=np.uint8, count=count)

        tr_img = _ler(arquivos["train_img"], 16, ">I", 60000 * 28 * 28).reshape(60000, 784) / 255.0
        tr_lbl = _ler(arquivos["train_lbl"], 8,  ">I", 60000)
        te_img = _ler(arquivos["test_img"],  16, ">I", 10000 * 28 * 28).reshape(10000, 784) / 255.0
        te_lbl = _ler(arquivos["test_lbl"],  8,  ">I", 10000)
        return (tr_img, tr_lbl), (te_img, te_lbl)

    def carregar_ou_treinar(self, epochs: int = 5) -> str:
        try:
            import sklearn  # noqa: F401
        except ImportError:
            return "scikit-learn nao instalado. Execute: pip install scikit-learn"

        # Tenta carregar modelo salvo
        if self.MODEL_PATH.exists():
            try:
                import pickle
                with open(self.MODEL_PATH, "rb") as f:
                    dados = pickle.load(f)
                self._modelo          = dados["modelo"]
                self._acuracia        = dados.get("acuracia")
                self._historico_treino = dados.get("historico", [])
                self._treinado        = True
                return f"Modelo carregado de {self.MODEL_PATH.name}"
            except Exception:
                pass

        print(f"{Fore.BLUE}  [NEURAL] Baixando MNIST e treinando {epochs} epocas (sklearn MLP)...")
        try:
            (tr_img, tr_lbl), (te_img, te_lbl) = self._carregar_mnist()
        except Exception as e:
            return f"Erro ao baixar MNIST: {e}"

        self._modelo = self._construir_modelo()
        if not self._modelo:
            return "Erro ao construir modelo (sklearn nao disponivel?)."

        self._historico_treino = []
        for ep in range(1, epochs + 1):
            self._modelo.max_iter = ep
            self._modelo.fit(tr_img, tr_lbl)
            acc_ep = self._modelo.score(te_img[:2000], te_lbl[:2000])
            self._historico_treino.append(acc_ep)
            print(f"{Fore.BLUE}  [NEURAL] Epoch {ep}/{epochs} — acc: {acc_ep:.2%}")

        self._acuracia = self._modelo.score(te_img, te_lbl)
        self._treinado = True

        import pickle
        with open(self.MODEL_PATH, "wb") as f:
            pickle.dump({
                "modelo": self._modelo,
                "acuracia": self._acuracia,
                "historico": self._historico_treino,
            }, f)
        return f"Treinamento concluido! Acuracia: {self._acuracia:.2%} | Salvo em {self.MODEL_PATH.name}"

    def atualizar(self, new_images, new_labels) -> str:
        if not self._treinado or not self._modelo:
            return "Modelo nao treinado. Use 'neural treinar' primeiro."
        try:
            imgs = np.array(new_images).reshape((-1, 784)).astype("float32") / 255.0
            self._modelo.fit(imgs, new_labels)
            import pickle
            with open(self.MODEL_PATH, "wb") as f:
                pickle.dump({
                    "modelo": self._modelo,
                    "acuracia": self._acuracia,
                    "historico": self._historico_treino,
                }, f)
            return f"Modelo atualizado com {len(new_labels)} exemplos."
        except Exception as e:
            return f"Erro: {e}"

    def status(self) -> str:
        if not self._treinado:
            return "  Nao treinado. Use: neural treinar"
        hist_str = " -> ".join(f"{a:.2%}" for a in self._historico_treino[-3:]) or "N/A"
        return (
            f"  Treinado    : Sim\n"
            f"  Acuracia    : {self._acuracia:.2%}\n"
            f"  Ultimas ep. : {hist_str}\n"
            f"  Arquivo     : {self.MODEL_PATH.name}"
        )


# ==============================================================
# TESTES AUTOMATIZADOS
# ==============================================================
