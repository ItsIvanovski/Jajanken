"""
Projet 1 — Roche-papier-ciseaux en réseau avec ESP32-C3 et MQTT
243-53A-MO — Interface usager de microcontrôleurs — Projet 1

Objectif : reprendre le jeu du laboratoire 3 et la console du laboratoire 4
pour jouer à deux joueurs, chacun avec son PC et son ESP32-C3.
  - le PC parle seulement en série à SA carte (LiaisonESP32 de liaison.py) ;
    ce sont les deux cartes qui s'échangent les coups par MQTT ;
  - analyser_ligne() découpe les lignes MSG: et LIEN: reçues de la carte ;
  - machine à états (une constante par état) : l'état change SEULEMENT dans
    changer_etat(), qui gère les boutons, la ligne d'instruction et la LED ;
  - le coup de l'adversaire qui ouvre reste caché (« ? ») jusqu'à notre réponse ;
  - journal horodaté : lignes envoyées (→), reçues (←) et événements (•).

Matériel : l'ESP32-C3 Super Mini exécute le firmware du projet (main.cpp).
Les dossiers images/ et sons/ du laboratoire 3 sont à côté du script.

Préparation : pip install pyserial PySide6
Fermez le moniteur série de PlatformIO avant de connecter cette interface.

Programmeurs : (noms de l'équipe)
Date de création : 2026-11-04
Dernière modification : 2026-11-04
"""

import sys
from pathlib import Path

import serial
from serial.tools import list_ports
from PySide6.QtCore import Qt, QSize, QTimer, QUrl, QTime
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QComboBox, QPushButton, QLabel, QLineEdit, QPlainTextEdit,
    QMessageBox
)

from liaison import LiaisonESP32

VITESSE = 115200        # sans effet sur l'USB natif de la C3, mais requis par pyserial
VID_ESPRESSIF = 0x303A  # identifiant USB d'Espressif : sert à repérer la carte
MANCHES_GAGNANTES = 3   # premier à 3 victoires (les égalités ne comptent pas)
DELAI_AFFICHAGE = 3000  # le résultat reste 3 s à l'écran (ms)

DOSSIER_IMAGES = Path(__file__).parent / "images"
DOSSIER_SONS = Path(__file__).parent / "sons"

CHOIX = ["roche", "papier", "ciseaux"]
BAT = {"roche": "ciseaux", "ciseaux": "papier", "papier": "roche"}  # clé bat valeur

# États de la partie (une constante par état)
DECONNECTE = "DECONNECTE"                # pas de liaison avec la carte
OUVRIR = "OUVRIR"                        # c'est à moi d'ouvrir la manche
ATTENTE_REPONSE = "ATTENTE_REPONSE"      # j'ai ouvert, j'attends le résultat
REPONDRE = "REPONDRE"                    # l'adversaire a ouvert, je réponds
ATTENTE_OUVERTURE = "ATTENTE_OUVERTURE"  # l'adversaire doit ouvrir
AFFICHAGE = "AFFICHAGE"                  # résultat affiché 3 s
PARTIE_TERMINEE = "PARTIE_TERMINEE"      # un joueur a 3 victoires

VERT = "color: #1e8e3e; font-weight: bold;"
ROUGE = "color: #d93025; font-weight: bold;"


def analyser_ligne(ligne):
    """Découpe une ligne reçue de la carte.

    "MSG:coup=j1;roche" -> ("MSG", "coup", "j1;roche")
    "LIEN:MQTT:OK"      -> ("LIEN", "MQTT", "OK")
    Retourne None si la ligne est vide, de débogage (#) ou mal formée.
    """
    ligne = ligne.strip()
    if not ligne or ligne.startswith("#"):
        return None
    if ligne.startswith("MSG:"):
        sous_topic, egal, message = ligne[4:].partition("=")  # coupe au premier =
        if egal and sous_topic:
            return ("MSG", sous_topic, message)
    elif ligne.startswith("LIEN:"):
        element, _, valeur = ligne[5:].partition(":")
        if element in ("WIFI", "MQTT") and valeur in ("OK", "ERREUR"):
            return ("LIEN", element, valeur)
    return None                                # préfixe inconnu ou ligne corrompue


class Fenetre(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roche - Papier - Ciseaux")
        self.setWindowIcon(QIcon(str(DOSSIER_IMAGES / "icone_jeu.png")))
        self.resize(600, 760)

        # --- Données de la partie ---
        self.etat = DECONNECTE
        self.joueur = "j1"
        self.adversaire = "j2"
        self.coup_adversaire = None      # coup de l'ouvreur adverse, gardé secret
        self.prochain_etat = None        # état après les 3 s d'AFFICHAGE
        self.victoires = self.defaites = self.egalites = 0
        self.wifi_ok = self.mqtt_ok = self.adversaire_en_ligne = False

        # --- Sons du laboratoire 3 : source réglée une seule fois ---
        self.son_victoire = self.creer_son("victoire.wav")
        self.son_defaite = self.creer_son("defaite.wav")
        self.son_egalite = self.creer_son("egalite.wav")

        # --- Liaison : son QTimer lit le port et émet les signaux ---
        self.liaison = LiaisonESP32()
        self.liaison.ligne_recue.connect(self.traiter_ligne)
        self.liaison.ligne_envoyee.connect(lambda ligne: self.journaliser("→", ligne))
        self.liaison.connexion_perdue.connect(self.connexion_perdue)

        # --- Groupe « Connexion » : port, joueur, équipe, connecter ---
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

        # --- Groupe « État » : Wi-Fi, Broker, Adversaire ---
        self.label_wifi = QLabel()
        self.label_broker = QLabel()
        self.label_adversaire = QLabel()

        groupe_etat = QGroupBox("État")
        layout_etat = QHBoxLayout(groupe_etat)
        for titre, label in (("Wi-Fi :", self.label_wifi),
                             ("Broker :", self.label_broker),
                             ("Adversaire :", self.label_adversaire)):
            layout_etat.addWidget(QLabel(titre))
            layout_etat.addWidget(label, 1)

        # --- Groupe « Partie » : instruction, choix, images, résultat, score ---
        self.label_instruction = QLabel()
        self.label_instruction.setAlignment(Qt.AlignCenter)
        self.label_instruction.setStyleSheet("font-size: 16px; font-weight: bold;")

        ligne_boutons = QHBoxLayout()
        self.boutons_choix = []              # pour les activer/bloquer ensemble
        for choix in CHOIX:
            bouton = QPushButton(choix.capitalize())
            bouton.setIcon(QIcon(str(DOSSIER_IMAGES / f"{choix}.png")))
            bouton.setIconSize(QSize(48, 48))
            # choix=choix « fige » la valeur, sinon les 3 lambdas joueraient « ciseaux »
            bouton.clicked.connect(lambda _=False, choix=choix: self.jouer(choix))
            ligne_boutons.addWidget(bouton)
            self.boutons_choix.append(bouton)

        self.image_vous = self.creer_zone_image()
        self.image_adversaire = self.creer_zone_image()
        ligne_images = QHBoxLayout()
        for titre, image in (("Vous", self.image_vous), ("Adversaire", self.image_adversaire)):
            colonne = QVBoxLayout()
            label_titre = QLabel(titre)
            label_titre.setAlignment(Qt.AlignCenter)
            colonne.addWidget(label_titre)
            colonne.addWidget(image, alignment=Qt.AlignCenter)
            ligne_images.addLayout(colonne)

        self.label_resultat = QLabel()
        self.label_resultat.setAlignment(Qt.AlignCenter)
        self.label_score = QLabel()
        self.label_score.setAlignment(Qt.AlignCenter)
        self.btn_nouvelle = QPushButton("Nouvelle partie")
        self.btn_nouvelle.clicked.connect(self.nouvelle_partie)

        groupe_partie = QGroupBox("Partie")
        layout_partie = QVBoxLayout(groupe_partie)
        layout_partie.addWidget(self.label_instruction)
        layout_partie.addLayout(ligne_boutons)
        layout_partie.addLayout(ligne_images)
        layout_partie.addWidget(self.label_resultat)
        layout_partie.addWidget(self.label_score)
        layout_partie.addWidget(self.btn_nouvelle)

        # --- Groupe « Journal » : lignes →, ← et événements • horodatés ---
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(500)     # évite que le journal grossisse sans fin
        self.groupe_journal = QGroupBox("Journal")
        layout_journal = QVBoxLayout(self.groupe_journal)
        layout_journal.addWidget(self.journal)

        self.btn_journal = QPushButton("Masquer le journal")
        self.btn_journal.clicked.connect(self.basculer_journal)
        self.btn_quitter = QPushButton("Quitter")
        self.btn_quitter.clicked.connect(self.close)   # passe par closeEvent()
        ligne_bas = QHBoxLayout()
        ligne_bas.addWidget(self.btn_journal)
        ligne_bas.addWidget(self.btn_quitter)

        # --- Assemblage de la fenêtre ---
        conteneur = QWidget()
        layout = QVBoxLayout(conteneur)
        layout.addWidget(groupe_connexion)
        layout.addWidget(groupe_etat)
        layout.addWidget(groupe_partie)
        layout.addWidget(self.groupe_journal, 1)
        layout.addLayout(ligne_bas)
        self.setCentralWidget(conteneur)

        self.remplir_ports()
        self.afficher_indicateurs()
        self.afficher_score()
        self.changer_etat(DECONNECTE)

    def creer_son(self, fichier):
        son = QSoundEffect(self)
        son.setSource(QUrl.fromLocalFile(str(DOSSIER_SONS / fichier)))
        son.setVolume(0.6)
        return son

    def creer_zone_image(self):
        image = QLabel()
        image.setFixedSize(110, 110)
        image.setAlignment(Qt.AlignCenter)
        image.setStyleSheet("font-size: 48px; font-weight: bold; border: 2px dashed #b0b0b0;")
        return image

    # ------------------------------------------------------------------ ports
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
            # Port absent ou déjà occupé (moniteur série de PlatformIO ouvert ?).
            QMessageBox.critical(self, "Port série", f"Ouverture impossible : {erreur}")
            return

        self.joueur = self.combo_joueur.currentText()
        self.adversaire = "j2" if self.joueur == "j1" else "j1"
        for w in (self.combo_ports, self.btn_actualiser, self.combo_joueur, self.champ_equipe):
            w.setEnabled(False)                # réglages verrouillés pendant la connexion
        self.btn_connecter.setText("Déconnecter")
        self.journaliser("•", f"Connecté à {nom} ({self.joueur}, {self.champ_equipe.text()})")

        # État initial : j1 ouvre, j2 attend
        self.reinitialiser_partie()
        self.changer_etat(OUVRIR if self.joueur == "j1" else ATTENTE_OUVERTURE)

    def deconnecter(self):
        self.changer_etat(DECONNECTE)          # envoie LED:OFF tant que le port est ouvert
        self.liaison.fermer()
        self.wifi_ok = self.mqtt_ok = self.adversaire_en_ligne = False
        self.afficher_indicateurs()
        for w in (self.combo_ports, self.btn_actualiser, self.combo_joueur, self.champ_equipe):
            w.setEnabled(True)
        self.btn_connecter.setText("Connecter")

    def connexion_perdue(self, erreur):
        # Câble débranché : retour à DECONNECTE et avertissement
        self.journaliser("•", f"Connexion perdue : {erreur}")
        self.deconnecter()
        QMessageBox.critical(self, "Port série", f"Connexion perdue : {erreur}")

    # ---------------------------------------------------------------- envoi
    def envoyer(self, commande):
        if self.liaison.est_ouverte:
            try:
                self.liaison.envoyer(commande)     # envoyer() ajoute le \n final
            except serial.SerialException:
                pass                               # la perte sera signalée par connexion_perdue

    def publier(self, sous_topic, message):
        # Ligne PUB:<sous-topic>=<message> : la carte publie sur MQTT
        self.envoyer(f"PUB:{sous_topic}={message}")

    # -------------------------------------------------------------- réception
    def traiter_ligne(self, ligne):
        self.journaliser("←", ligne)
        resultat = analyser_ligne(ligne)
        if resultat is None:
            return                             # vide, débogage ou corrompue : ignorée
        type_ligne, sous_topic, message = resultat

        if type_ligne == "LIEN":
            if sous_topic == "WIFI":
                self.wifi_ok = (message == "OK")
            else:
                self.mqtt_ok = (message == "OK")
            self.afficher_indicateurs()
            self.rafraichir()
        elif sous_topic == f"{self.adversaire}/etat":
            self.adversaire_en_ligne = (message == "en ligne")   # « hors ligne » = testament
            self.afficher_indicateurs()
            self.rafraichir()
        elif sous_topic == "coup":
            self.recevoir_coup(message)
        elif sous_topic == "resultat":
            self.recevoir_resultat(message)
        # Autres sous-topics (dont l'écho de notre propre etat) : ignorés

    def recevoir_coup(self, message):
        joueur, _, coup = message.partition(";")
        if joueur != self.adversaire or coup not in CHOIX:
            return                             # écho de mon coup ou coup invalide
        if self.etat == PARTIE_TERMINEE:
            # L'adversaire a relancé une partie avant nous : on repart aussi
            self.reinitialiser_partie()
        elif self.etat != ATTENTE_OUVERTURE:
            return
        self.coup_adversaire = coup            # mémorisé, JAMAIS affiché avant ma réponse
        self.vider_images()
        self.image_adversaire.setText("?")
        self.changer_etat(REPONDRE)

    def recevoir_resultat(self, message):
        if self.etat != ATTENTE_REPONSE:
            return                             # écho de mon propre résultat
        parties = message.split(";")
        if (len(parties) != 3 or parties[0] not in CHOIX or parties[1] not in CHOIX
                or parties[2] not in ("j1", "j2", "egalite")):
            return                             # résultat mal formé
        coup_ouvreur, coup_repondeur, gagnant = parties
        # J'étais l'ouvreur ; le répondeur ouvrira la manche suivante
        self.terminer_manche(coup_ouvreur, coup_repondeur, gagnant, ATTENTE_OUVERTURE)

    # ------------------------------------------------------------------ jeu
    def jouer(self, choix):
        """Slot commun aux trois boutons de choix."""
        if self.etat == OUVRIR:
            self.publier("coup", f"{self.joueur};{choix}")
            self.vider_images()
            self.afficher_image(self.image_vous, choix)
            self.image_adversaire.setText("?")
            self.changer_etat(ATTENTE_REPONSE)
        elif self.etat == REPONDRE:
            # C'est le répondeur qui calcule le gagnant et publie le résultat
            gagnant = self.determiner_gagnant(self.coup_adversaire, choix)
            self.publier("resultat", f"{self.coup_adversaire};{choix};{gagnant}")
            self.terminer_manche(choix, self.coup_adversaire, gagnant, OUVRIR)

    def determiner_gagnant(self, coup_ouvreur, mon_coup):
        """Règles du laboratoire 3 : retourne "j1", "j2" ou "egalite"."""
        if coup_ouvreur == mon_coup:
            return "egalite"
        if BAT[mon_coup] == coup_ouvreur:
            return self.joueur
        return self.adversaire

    def terminer_manche(self, mon_coup, coup_adversaire, gagnant, prochain_etat):
        self.afficher_image(self.image_vous, mon_coup)
        self.afficher_image(self.image_adversaire, coup_adversaire)

        if gagnant == "egalite":
            self.egalites += 1
            self.son_egalite.play()
            self.label_resultat.setText("Égalité !")
        elif gagnant == self.joueur:
            self.victoires += 1
            self.son_victoire.play()
            self.label_resultat.setText("Vous gagnez la manche !")
        else:
            self.defaites += 1
            self.son_defaite.play()
            self.label_resultat.setText("L'adversaire gagne la manche.")
        self.afficher_score()

        self.prochain_etat = prochain_etat     # à régler AVANT changer_etat (LED)
        self.changer_etat(AFFICHAGE)
        # Appel unique dans 3 s, sans bloquer la fenêtre (contrairement à time.sleep)
        QTimer.singleShot(DELAI_AFFICHAGE, self.fin_affichage)

    def fin_affichage(self):
        if self.etat != AFFICHAGE:
            return                             # déconnecté pendant les 3 s
        if self.partie_finie():
            gagne = self.victoires >= MANCHES_GAGNANTES
            self.label_resultat.setText(
                f"Vous remportez la partie {self.victoires}-{self.defaites} !" if gagne
                else f"L'adversaire remporte la partie {self.defaites}-{self.victoires}.")
            self.changer_etat(PARTIE_TERMINEE)
        else:
            self.vider_images()
            self.label_resultat.setText("")
            self.changer_etat(self.prochain_etat)

    def partie_finie(self):
        return max(self.victoires, self.defaites) >= MANCHES_GAGNANTES

    def nouvelle_partie(self):
        self.reinitialiser_partie()
        self.changer_etat(OUVRIR if self.joueur == "j1" else ATTENTE_OUVERTURE)

    def reinitialiser_partie(self):
        self.victoires = self.defaites = self.egalites = 0
        self.coup_adversaire = None
        self.vider_images()
        self.label_resultat.setText("")
        self.afficher_score()

    # ----------------------------------------------------- machine à états
    def changer_etat(self, etat):
        """SEUL endroit où l'état change : LED, boutons et instruction."""
        if etat != self.etat:
            self.journaliser("•", f"{self.etat} → {etat}")
        self.etat = etat

        # LED allumée seulement quand c'est à moi de jouer (en AFFICHAGE :
        # si c'est moi qui ouvre ensuite et que la partie n'est pas finie)
        mon_tour = etat in (OUVRIR, REPONDRE) or (
            etat == AFFICHAGE and self.prochain_etat == OUVRIR and not self.partie_finie())
        self.envoyer("LED:ON" if mon_tour else "LED:OFF")
        self.rafraichir()

    def rafraichir(self):
        """Active ou bloque les boutons et met à jour la ligne d'instruction."""
        jeu_possible = self.mqtt_ok and self.adversaire_en_ligne
        actifs = self.etat in (OUVRIR, REPONDRE) and jeu_possible
        for bouton in self.boutons_choix:
            bouton.setEnabled(actifs)
        self.btn_nouvelle.setEnabled(self.etat == PARTIE_TERMINEE)

        num = self.adversaire[1]               # "j2" -> "2"
        instructions = {
            DECONNECTE: "Connectez-vous à la carte.",
            OUVRIR: "À vous d'ouvrir la manche !",
            ATTENTE_REPONSE: f"En attente de la réponse du joueur {num}…",
            REPONDRE: f"Le joueur {num} a joué : répondez !",
            ATTENTE_OUVERTURE: f"En attente du coup du joueur {num}…",
            AFFICHAGE: "Fin de la manche…",
            PARTIE_TERMINEE: "Partie terminée : cliquez sur « Nouvelle partie ».",
        }
        texte = instructions[self.etat]
        if self.etat in (OUVRIR, REPONDRE, ATTENTE_REPONSE, ATTENTE_OUVERTURE) and not jeu_possible:
            texte = "Broker non connecté : jeu bloqué" if not self.mqtt_ok \
                else "Adversaire hors ligne : jeu bloqué"
        self.label_instruction.setText(texte)

    # -------------------------------------------------------------- affichage
    def afficher_indicateurs(self):
        for label, ok in ((self.label_wifi, self.wifi_ok),
                          (self.label_broker, self.mqtt_ok),
                          (self.label_adversaire, self.adversaire_en_ligne)):
            label.setText("en ligne" if ok else "hors ligne")
            label.setStyleSheet(VERT if ok else ROUGE)

    def afficher_score(self):
        self.label_score.setText(f"Victoires : {self.victoires}   Défaites : {self.defaites}"
                                 f"   Égalités : {self.egalites}")

    def afficher_image(self, label, choix):
        pixmap = QPixmap(str(DOSSIER_IMAGES / f"{choix}.png"))
        label.setPixmap(pixmap.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def vider_images(self):
        self.image_vous.clear()
        self.image_adversaire.clear()

    def journaliser(self, symbole, texte):
        heure = QTime.currentTime().toString("HH:mm:ss")
        self.journal.appendPlainText(f"{heure} {symbole} {texte}")

    def basculer_journal(self):
        visible = not self.groupe_journal.isVisible()
        self.groupe_journal.setVisible(visible)
        self.btn_journal.setText("Masquer le journal" if visible else "Afficher le journal")

    def closeEvent(self, evenement):
        self.deconnecter()                     # éteint la LED et ferme le port
        super().closeEvent(evenement)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = Fenetre()
    fenetre.show()
    sys.exit(app.exec())