"""
243-53A-MO - Interface usager de microcontrôleurs

Projet 1 — Liaison série avec l'ESP32-C3 (fichier fourni)
====================================================================

La classe LiaisonESP32 regroupe tout ce qui touche au port série : elle est
reprise du laboratoire 4, avec deux ajouts pour ce laboratoire :

- la lecture est faite par un QTimer interne (toutes les 50 ms) : chaque
  ligne reçue est annoncée par le signal ligne_recue, ce qui évite à la
  fenêtre de gérer le minuteur elle-même ;
- une méthode publier() qui envoie à la carte la ligne PUB:<sous-topic>=<message>
  (protocole du projet 1).

La fenêtre ne connaît ni pyserial, ni le détail des lignes PUB: : elle appelle
seulement liaison.publier("coup", "j1;roche"), par exemple.

Programmeur : Guillaume Beaulieu
Date de création : 2026-10-22
Dernière modification : 2026-10-22
"""

import serial
from PySide6.QtCore import QObject, QTimer, Signal


def ouvrir_port(nom, vitesse=115200, timeout=0.1):
    """Ouvre le port série sans redémarrer la carte (voir laboratoire 4)."""
    port = serial.Serial()          # objet fermé : on règle les attributs d'abord
    port.port = nom
    port.baudrate = vitesse
    port.timeout = timeout
    port.dtr = False                # sur l'USB natif de la C3, DTR et RTS
    port.rts = False                # peuvent redémarrer la carte à l'ouverture
    port.open()
    return port


class LiaisonESP32(QObject):
    ligne_recue = Signal(str)           # une ligne reçue de la carte (sans le \n)
    ligne_envoyee = Signal(str)         # une ligne envoyée à la carte (pour le journal)
    connexion_perdue = Signal(str)      # le câble a été débranché ; texte de l'erreur

    def __init__(self, parent=None):
        super().__init__(parent)
        self.port = None
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(50)
        self.minuteur.timeout.connect(self._lire)

    @property
    def est_ouverte(self):
        return self.port is not None and self.port.is_open

    def ouvrir(self, nom, vitesse=115200):
        """Ouvre le port et démarre la lecture. Lève serial.SerialException en cas d'échec."""
        self.port = ouvrir_port(nom, vitesse)
        self.minuteur.start()

    def fermer(self):
        self.minuteur.stop()
        if self.port is not None:
            try:
                self.port.close()
            except (serial.SerialException, OSError):
                pass
        self.port = None

    def envoyer(self, commande):
        """Envoie une ligne de texte à la carte (le \\n final est ajouté ici)."""
        if not self.est_ouverte:
            return
        try:
            self.port.write((commande + "\n").encode())
        except (serial.SerialException, OSError) as erreur:
            self._perdue(str(erreur))
            return
        self.ligne_envoyee.emit(commande)

    def lire_lignes(self):
        """Retourne la liste des lignes complètes reçues, sans bloquer."""
        lignes = []
        while self.port.in_waiting:
            ligne = self.port.readline().decode(errors="ignore").strip()
            if ligne:
                lignes.append(ligne)
        return lignes

    def _lire(self):
        """Appelée par le QTimer : annonce chaque ligne reçue par un signal."""
        try:
            lignes = self.lire_lignes()
        except (serial.SerialException, OSError) as erreur:
            self._perdue(str(erreur))
            return
        for ligne in lignes:
            self.ligne_recue.emit(ligne)

    def _perdue(self, message):
        self.fermer()
        self.connexion_perdue.emit(message)

    def publier(self, sous_topic, message):
        """Demande à la carte de publier le message sur 53A/jeu/<EQUIPE>/<sous_topic>."""
        self.envoyer(f"PUB:{sous_topic}={message}")
