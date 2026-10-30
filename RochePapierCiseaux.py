"""
243-53A-MO - Interface usager de microcontrôleurs
 
Exercice 8 — Jeu roche-papier-ciseau contre l'ordinateur
============================================================
 
Concepts clés :
- Les trois choix sont représentés par des images (QIcon sur les
  boutons, QPixmap dans les QLabel) plutôt que par du texte.
- random.choice() tire le coup de l'ordinateur au hasard parmi les
  trois options, une fois par manche.
- Les trois boutons sont connectés à UNE SEULE méthode plutôt qu'à
  trois méthodes presque identiques, grâce à une lambda qui capture
  le choix du joueur en argument (piège classique : il faut "figer" la
  valeur avec un paramètre par défaut, sinon les trois lambdas
  partagent la même variable de boucle).
- Le score cumulatif est simplement mis à jour dans des attributs
  d'instance et réaffiché après chaque manche.
- QTimer.singleShot(délai_ms, méthode) exécute une méthode une seule
  fois après un délai, sans bloquer l'interface — ici, il efface les
  choix et le résultat 3 secondes après chaque manche.
- setWindowIcon(QIcon(chemin)) définit l'icône affichée dans la barre
  de titre et la barre des tâches (icone_jeu.png, dans images/).
- QSoundEffect (QtMultimedia) joue un court effet sonore sans bloquer
  l'interface ; sa source se règle une seule fois avec setSource(), puis
  chaque appel à .play() rejoue le son depuis le début — un son distinct
  pour la victoire du joueur, la victoire de l'ordinateur et l'égalité.
- bouton.setEnabled(False/True) empêche les clics sans cacher le
  bouton : les trois boutons de choix sont désactivés pendant les 3
  secondes d'affichage du résultat, puis réactivés dans effacer_manche().
- QApplication.instance() récupère l'unique instance de l'application
  déjà créée dans __main__ ; .quit() ferme proprement l'application
  depuis un bouton, sans passer par le X de la fenêtre.
 
Ce script suppose un dossier images/ contenant roche.png, papier.png,
ciseaux.png et icone_jeu.png, ainsi qu'un dossier sons/ contenant
victoire.wav, defaite.wav et egalite.wav, au même endroit que le script.
 
Programmeur : Guillaume Beaulieu
Date de création : 2026-07-29
Dernière modification : 2026-07-29
"""
 
import sys
import random
import serial
from serial.tools import list_ports
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QComboBox,
    QLineEdit,
    QMessageBox,
)

from liaison import LiaisonESP32
VITESSE = 115200
VID_ESPRESSIF = 0x303A
 
DOSSIER_IMAGES = Path(__file__).parent / "images" #__file__ est le chemin du script en cours d'exécution, Path(__file__).parent est le dossier contenant ce script.
DOSSIER_SONS = Path(__file__).parent / "sons"
CHOIX = ["roche", "papier", "ciseaux"]
 
# Règles classiques : chaque clé bat la valeur associée
BAT = {
    "roche": "ciseaux",
    "ciseaux": "papier",
    "papier": "roche",
}
 
 
class FenetreJeu(QMainWindow):
    def __init__(self):
        super().__init__() #Appel du constructeur de la classe parente QMainWindow pour initialiser correctement la fenêtre principale.
        self.setWindowTitle("Roche - Papier - Ciseaux")
        self.setWindowIcon(QIcon(str(DOSSIER_IMAGES / "icone_jeu.png"))) #QIcon est utilisé pour définir l'icône de la fenêtre, qui sera affichée dans la barre de titre et la barre des tâches. L'icône est chargée depuis le fichier icone_jeu.png situé dans le dossier images/.
        self.resize(560, 520)
 
        # Score cumulatif conservé sur toute la session de jeu
        self.victoires_joueur1 = 0
        self.victoires_joueur2 = 0
        self.egalites = 0
 
        # Effet sonore joué quand le joueur gagne une manche : la source
        # est réglée une seule fois ici, .play() sera appelé à chaque victoire
        self.son_victoire = QSoundEffect() #QSoundEffect est une classe de QtMultimedia qui permet de jouer des sons courts sans bloquer l'interface utilisateur. Elle est utilisée ici pour jouer un son spécifique lorsque le joueur gagne une manche.
        self.son_victoire.setSource(QUrl.fromLocalFile(str(DOSSIER_SONS / "victoire.wav")))
        self.son_victoire.setVolume(0.6) #Volume du son réglé à 60% pour ne pas être trop fort.
 
        # Même principe pour le son joué quand l'ordinateur gagne
        self.son_defaite = QSoundEffect()
        self.son_defaite.setSource(QUrl.fromLocalFile(str(DOSSIER_SONS / "defaite.wav")))
        self.son_defaite.setVolume(0.6)
 
        # Et pour le son joué en cas d'égalité
        self.son_egalite = QSoundEffect()
        self.son_egalite.setSource(QUrl.fromLocalFile(str(DOSSIER_SONS / "egalite.wav")))
        self.son_egalite.setVolume(0.6)
 
        conteneur = QWidget()
        self.setCentralWidget(conteneur) #On crée un QWidget conteneur qui servira de widget central pour la fenêtre principale. Tous les autres widgets (boutons, labels, etc.) seront ajoutés à ce conteneur.
        layout_principal = QVBoxLayout() #On crée un QVBoxLayout pour organiser les widgets verticalement dans le conteneur. Ce layout sera utilisé pour disposer les différents éléments de l'interface utilisateur (boutons, labels, etc.) de haut en bas.
        conteneur.setLayout(layout_principal) #On assigne le layout principal au conteneur, ce qui permet de gérer automatiquement la disposition des widgets enfants ajoutés à ce layout.

        self.liaison = LiaisonESP32()
        self.liaison.connexion_perdue.connect(self.connexion_perdue)
 
        # --- Groupe « Connexion » : tout en haut de la fenêtre ---
        self.combo_ports = QComboBox()
        self.btn_actualiser = QPushButton("Actualiser")
        self.btn_actualiser.clicked.connect(self.remplir_ports)
 
        self.combo_joueur = QComboBox()
        self.combo_joueur.addItems(["j1", "j2"])
 
        self.champ_equipe = QLineEdit("equipe1")
 
        self.btn_connecter = QPushButton("Connecter")
        self.btn_connecter.clicked.connect(self.basculer_connexion)
 
        groupe_connexion = QGroupBox("Connexion")
        grille = QGridLayout(groupe_connexion)
        grille.addWidget(QLabel("Port :"), 0, 0)
        grille.addWidget(self.combo_ports, 0, 1)
        grille.addWidget(self.btn_actualiser, 0, 2)
        grille.addWidget(QLabel("Joueur :"), 1, 0)
        grille.addWidget(self.combo_joueur, 1, 1)
        grille.addWidget(QLabel("Équipe :"), 2, 0)
        grille.addWidget(self.champ_equipe, 2, 1)
        grille.addWidget(self.btn_connecter, 1, 2, 2, 1)   # occupe les lignes 1 et 2
        grille.setColumnStretch(1, 1)
 
        layout_principal.addWidget(groupe_connexion)       # AVANT les boutons de choix
        self.remplir_ports()


        # --- Rangée des boutons de choix (avec icônes) ---
        layout_boutons = QHBoxLayout()
        layout_principal.addLayout(layout_boutons)
 
        # Conservés dans une liste pour pouvoir les désactiver/réactiver
        # tous ensemble pendant le délai d'affichage de la manche
        self.boutons_choix = []
 
        for choix in CHOIX:
            bouton = QPushButton(choix.capitalize()) #On crée un QPushButton pour chaque choix (roche, papier, ciseaux) avec le texte du bouton correspondant au choix, capitalisé (première lettre en majuscule).
            bouton.setIcon(QIcon(str(DOSSIER_IMAGES / f"{choix}.png"))) #On définit l'icône du bouton en utilisant un QIcon créé à partir de l'image correspondante (roche.png, papier.png, ciseaux.png) située dans le dossier images/. L'icône est affichée à côté du texte du bouton.
            bouton.setIconSize(QSize(48, 48)) #On définit la taille de l'icône du bouton à 48x48 pixels pour que l'image soit affichée correctement et de manière uniforme sur tous les boutons.
            # On "fige" la valeur de choix avec un paramètre par défaut
            # (choix=choix) : sinon, les trois lambdas partageraient la
            # même variable de boucle et joueraient toutes "ciseaux".
            bouton.clicked.connect(lambda _=False, choix=choix: self.jouer(choix))
            layout_boutons.addWidget(bouton) #On ajoute le bouton au layout horizontal des boutons de choix, ce qui les dispose côte à côte dans l'interface utilisateur.
            self.boutons_choix.append(bouton) #On ajoute le bouton à la liste self.boutons_choix pour pouvoir les désactiver ou réactiver tous ensemble pendant le délai d'affichage du résultat de la manche. Cela permet de gérer l'état des boutons de manière centralisée.
 
        # --- Rangée d'affichage des deux images choisies ---
        layout_images = QHBoxLayout()
        layout_principal.addLayout(layout_images)
 
        self.label_choix_joueur1 = QLabel("Votre choix")
        self.label_choix_joueur1.setAlignment(Qt.AlignCenter)
        self.label_choix_joueur2 = QLabel("Joueur 2")
        self.label_choix_joueur2.setAlignment(Qt.AlignCenter)
        layout_images.addWidget(self.label_choix_joueur1)
        layout_images.addWidget(self.label_choix_joueur2)
 
        # --- Résultat de la manche et score ---
        self.label_resultat = QLabel("Faites votre choix !")
        self.label_resultat.setAlignment(Qt.AlignCenter)
        layout_principal.addWidget(self.label_resultat)
 
        self.label_score = QLabel()
        self.label_score.setAlignment(Qt.AlignCenter)
        layout_principal.addWidget(self.label_score)
        self.mettre_a_jour_score()
 
        # --- Bouton de réinitialisation du score, en bas de la fenêtre ---
        self.bouton_reinitialiser = QPushButton("Réinitialiser le score")
        self.bouton_reinitialiser.clicked.connect(self.reinitialiser_score)
        layout_principal.addWidget(self.bouton_reinitialiser)
 
        # --- Bouton Quitter, tout en bas de la fenêtre ---
        self.bouton_quitter = QPushButton("Quitter")
        # QApplication.instance() récupère l'unique instance de l'application
        # déjà créée dans le bloc __main__ ; .quit() ferme proprement
        # l'application (équivalent à fermer la fenêtre avec le X).
        self.bouton_quitter.clicked.connect(QApplication.instance().quit)
        layout_principal.addWidget(self.bouton_quitter)

    def remplir_ports(self):
        self.combo_ports.clear()
        for port in list_ports.comports():
            self.combo_ports.addItem(f"{port.device} — {port.description}", port.device)
            if port.vid == VID_ESPRESSIF:
                self.combo_ports.setCurrentIndex(self.combo_ports.count() - 1)
 
    def basculer_connexion(self):
        if self.liaison.est_ouverte:
            self.deconnecter()
        else:
            self.connecter()
 
    def connecter(self):
        nom = self.combo_ports.currentData()
        if nom is None:
            QMessageBox.warning(self, "Port série", "Aucun port série détecté.")
            return
        try:
            self.liaison.ouvrir(nom, VITESSE)
        except serial.SerialException as erreur:
            QMessageBox.critical(self, "Port série", f"Ouverture impossible : {erreur}")
            return
        self.btn_connecter.setText("Déconnecter")
        # On verrouille les réglages pendant la connexion
        for w in (self.combo_ports, self.btn_actualiser, self.combo_joueur, self.champ_equipe):
            w.setEnabled(False)
 
    def deconnecter(self):
        self.liaison.fermer()
        self.btn_connecter.setText("Connecter")
        for w in (self.combo_ports, self.btn_actualiser, self.combo_joueur, self.champ_equipe):
            w.setEnabled(True)
 
    def connexion_perdue(self, erreur):
        self.deconnecter()
        QMessageBox.critical(self, "Port série", f"Connexion perdue : {erreur}")
 
    def jouer(self, choix_joueur):
        """Slot commun aux trois boutons : reçoit le choix du joueur en
        paramètre, tire le coup de l'ordinateur, compare et affiche."""
        choix_joueur2 = random.choice(CHOIX) #On utilise random.choice() pour sélectionner au hasard un choix parmi les trois options (roche, papier, ciseaux) pour l'ordinateur. Cela simule le comportement de l'ordinateur dans le jeu, en lui donnant une chance égale de choisir n'importe quelle option à chaque manche.
 
        self.afficher_choix(self.label_choix_joueur1, choix_joueur) #On appelle la méthode afficher_choix() pour mettre à jour l'affichage de l'image correspondant au choix du joueur dans le QLabel self.label_choix_joueur. Cela permet de montrer visuellement le choix du joueur à l'écran.
        self.afficher_choix(self.label_choix_joueur2, choix_joueur2) #On appelle la méthode afficher_choix() pour mettre à jour l'affichage de l'image correspondant au choix de l'ordinateur dans le QLabel self.label_choix_ordinateur. Cela permet de montrer visuellement le choix de l'ordinateur à l'écran.
 
        resultat = self.determiner_gagnant(choix_joueur, choix_joueur2) #On appelle la méthode determiner_gagnant() pour comparer les choix du joueur et de l'ordinateur selon les règles du jeu. Cette méthode met à jour le score en fonction du résultat de la manche et retourne un texte décrivant le résultat (victoire, défaite ou égalité).
        self.label_resultat.setText(resultat)
        self.mettre_a_jour_score()
 
        # On désactive les trois boutons le temps de l'affichage du
        # résultat, pour empêcher un nouveau choix avant la fin du délai
        for bouton in self.boutons_choix:
            bouton.setEnabled(False)
 
        # QTimer.singleShot() planifie un appel unique après un délai
        # (en millisecondes) SANS bloquer l'interface — contrairement à
        # time.sleep(), la fenêtre reste réactive pendant l'attente.
        # Ici, on efface les images et le message de résultat 3 secondes
        # après la fin de la manche, et on réactive les boutons.
        QTimer.singleShot(3000, self.effacer_manche)
 
    def effacer_manche(self):
        """Remet les images des choix et le message de résultat à leur
        état initial, 3 secondes après la fin d'une manche, et réactive
        les boutons de choix."""
        self.label_choix_joueur1.clear()
        self.label_choix_joueur1.setText("Votre choix")
        self.label_choix_joueur2.clear()
        self.label_choix_joueur2.setText("Joueur 2")
        self.label_resultat.setText("Faites votre choix !")
 
        for bouton in self.boutons_choix:
            bouton.setEnabled(True)
 
    def afficher_choix(self, label, choix):
        pixmap = QPixmap(str(DOSSIER_IMAGES / f"{choix}.png"))
        # On utilise scaled() pour redimensionner l'image à 80x80 pixels tout en conservant le ratio d'aspect original (Qt.KeepAspectRatio) et en appliquant un lissage (Qt.SmoothTransformation) pour éviter les effets de pixellisation.
        label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
 
    def determiner_gagnant(self, choix_joueur1, choix_joueur2):
        """Compare les deux choix selon les règles classiques et met à
        jour le score. Retourne le texte de résultat à afficher."""
        if choix_joueur1 == choix_joueur2:
            self.egalites += 1
            self.son_egalite.play()
            return "Égalité !"
 
        if BAT[choix_joueur1] == choix_joueur2:
            self.victoires_joueur1 += 1
            self.son_victoire.play()
            return "Vous gagnez cette manche !"
 
        self.victoires_joueur2 += 1
        self.son_defaite.play()
        return "Le joueur 2 gagne cette manche."
 
    def mettre_a_jour_score(self):
        self.label_score.setText(
            f"Victoires — Vous : {self.victoires_joueur1}   "
            f"Joueur 2 : {self.victoires_joueur2}   "
            f"Égalités : {self.egalites}"
        )
 
    def reinitialiser_score(self):
        """Slot du bouton Réinitialiser : remet les trois compteurs à
        zéro et rafraîchit l'affichage, sans toucher à la manche en cours."""
        self.victoires_joueur1 = 0
        self.victoires_joueur2 = 0
        self.egalites = 0
        self.mettre_a_jour_score()
 
 
if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = FenetreJeu()
    fenetre.show()
    sys.exit(app.exec())