#include <Arduino.h>        // fonctions de base : pinMode, digitalWrite, millis...
#include <WiFi.h>           // connexion au réseau Wi-Fi de l'ESP32
#include <PubSubClient.h>   // client MQTT (publier, s'abonner)
/*
  243-53A-MO — Interface usager de microcontrôleurs — Projet 1 (code à compléter)

  ESP32-C3 Super Mini : pont entre le PC (port série USB) et le broker MQTT.
  La carte ne connaît rien du jeu : elle relaie les lignes dans les deux sens.

  PC -> carte (port série, une ligne terminée par \n) :
    PUB:<sous-topic>=<message>   publie sur 53A/jeu/<EQUIPE>/<sous-topic>
    LED:ON / LED:OFF             allume ou éteint la LED intégrée

  carte -> PC :
    MSG:<sous-topic>=<message>   un message MQTT vient d'arriver
    LIEN:WIFI:OK                 Wi-Fi connecté
    LIEN:MQTT:OK / LIEN:MQTT:ERREUR   état de la connexion au broker
    # texte                      débogage (l'interface l'ignore)

  MQTT : 53A/jeu/<EQUIPE>/<JOUEUR>/etat   « en ligne » (retenu) ; « hors ligne »
         est publié par le broker (testament) si la carte disparaît.

  Programme non bloquant : aucun delay() ; millis() mesure les délais et
  mqtt.loop() est appelé à chaque tour de loop().

  CODE À COMPLÉTER : chaque ____ (quatre soulignés) est un trou. Remplacez-le par le
  morceau de code manquant, d'après le commentaire qui le suit. Le programme ne
  compile pas tant qu'il reste un ____.
    TODO 1  messageRecu()    : relayer un message MQTT reçu vers le PC
    TODO 2  traiterLigne()   : exécuter une commande reçue du PC
    TODO 3  lireSerie()      : lire le port série sans jamais bloquer
    TODO 4  connecterMqtt()  : connexion au broker avec testament
    TODO 5  rappelerEtat()   : répéter l'état de la liaison au PC
    TODO 6  loop()           : reconnexion, mqtt.loop(), lecture série, rappel
  Les réglages, les variables et setup() sont fournis.

  Programmeur : Guillaume Beaulieu
  Date de création : 2026-10-22
  Dernière modification : 2026-10-22
*/

// ---------------------------------------------------------------- réglages
// À adapter : votre équipe, votre joueur et votre local
const char* EQUIPE = "gb";                   // nom court, sans espace (même valeur que dans l'interface)
const char* JOUEUR = "j1";                   // "j1" ou "j2"

const char* WIFI_SSID = "TGE-C3521";         // Local C-3521
// const char* WIFI_SSID = "TGE-C3516";      // Local C-3516
const char* WIFI_MDP  = "Tge2026++";         // même mot de passe dans les deux locaux

const char* BROKER    = "10.35.21.5";        // Local C-3521 (Raspberry Pi)
// const char* BROKER = "10.35.16.5";        // Local C-3516 (Raspberry Pi)
const int   PORT_MQTT = 1883;

const int PIN_LED = 8;                       // LED bleue intégrée (logique inversée : LOW = allumée)

const unsigned long DELAI_RECONNEXION_MQTT = 2000;   // ms entre deux tentatives de connexion
const unsigned long DELAI_RAPPEL_ETAT = 3000;        // ms entre deux rappels de l'état au PC

// ---------------------------------------------------------------- objets globaux
WiFiClient wifi;
PubSubClient mqtt(wifi);

String base;                // « 53A/jeu/<EQUIPE>/ » : préfixe de tous les topics
String topicEtat;           // « 53A/jeu/<EQUIPE>/<JOUEUR>/etat » : état de CETTE carte
String sousTopicAdversaire; // « j2/etat » si JOUEUR vaut j1, « j1/etat » sinon
String etatAdversaire;      // dernier « en ligne » / « hors ligne » reçu pour l'adversaire
String ligneSerie;          // ligne en cours de réception depuis le PC
bool wifiAnnonce = false;   // LIEN:WIFI:OK déjà envoyé depuis la dernière connexion
unsigned long dernierEssaiMqtt = 0;
unsigned long dernierRappel = 0;

// ---------------------------------------------------------------- réception MQTT
// Appelée par mqtt.loop() pour chaque message reçu. On ne filtre rien : même
// l'écho de nos propres publications est relayé au PC.
void messageRecu(char* topic, byte* payload, unsigned int longueur) {
  // TODO 1 : remplacer chaque ____
  String texte;
  for (unsigned int i = 0; i < ____; i++) {              // payload n'est PAS terminé par \0 : on utilise sa longueur
    texte += (char)payload[i];
  }
  String sousTopic = String(topic).substring(base.____());   // retire le préfixe « base » (méthode qui donne sa longueur)
  if (sousTopic == ____) {                               // c'est l'état de l'adversaire : on le garde
    etatAdversaire = texte;
  }
  Serial.print("MSG:");
  Serial.print(____);                                    // le sous-topic
  Serial.print("=");
  Serial.println(____);                                  // le texte du message
}

// ---------------------------------------------------------------- commandes du PC
// Exécute une ligne complète (sans le \n) reçue du PC.
void traiterLigne(String ligne) {
  // TODO 2 : remplacer chaque ____
  ligne.____();                                          // enlève les espaces et le \r aux extrémités
  if (ligne.length() == 0) return;

  if (ligne.startsWith(____)) {                          // la commande de publication « PUB: » (entre guillemets)
    String reste = ligne.substring(____);                // ce qui suit « PUB: » (nombre de caractères du préfixe)
    int egal = reste.indexOf(____);                      // position du PREMIER caractère « = » (entre apostrophes)
    if (egal < 1) {                                      // pas de « = », ou sous-topic vide
      Serial.println("# PUB mal formée");
      return;
    }
    String sousTopic = reste.substring(0, ____);         // tout ce qui précède le « = »
    String message = reste.substring(egal + ____);       // tout ce qui suit le « = »
    if (mqtt.connected()) {
      mqtt.publish((base + ____).c_str(), message.c_str());   // le sous-topic
    } else {
      Serial.println("# MQTT non connecté : message perdu");
    }
    return;
  }

  if (ligne == "LED:ON") {
    digitalWrite(PIN_LED, ____);                         // logique inversée : allumée = LOW ou HIGH ?
  } else if (ligne == "LED:OFF") {
    digitalWrite(PIN_LED, ____);
  } else {
    Serial.println("# commande inconnue");
  }
}

// Lit les octets disponibles sans jamais attendre.
void lireSerie() {
  // TODO 3 : remplacer chaque ____
  while (Serial.____() > 0) {                            // il reste des octets à lire
    char c = Serial.____();                              // lit UN octet
    if (c == ____) {                                     // le caractère de fin de ligne (entre apostrophes)
      traiterLigne(ligneSerie);
      ligneSerie = "";
    } else if (c != '\r') {
      ligneSerie += c;
    }
  }
}

// ---------------------------------------------------------------- MQTT
void connecterMqtt() {
  // TODO 4 : remplacer chaque ____
  // Identifiant unique : deux clients avec le même identifiant s'éjectent
  String id = "esp32c3-" + String(JOUEUR) + "-" + WiFi.macAddress();

  // connect(identifiant, topicTestament, qos, retenu, messageTestament)
  // Les quatre derniers arguments sont le TESTAMENT : si la carte disparaît sans se
  // déconnecter, le broker publie « hors ligne » à sa place.
  if (mqtt.connect(id.c_str(), ____, 0, ____, "____")) {     // topic de l'état, retenu (true/false), message du testament
    mqtt.publish(topicEtat.c_str(), "____", ____);           // « en ligne », en message retenu
    mqtt.subscribe((base + "____").c_str());                 // tous les sous-topics de l'équipe (joker)
    Serial.println("LIEN:MQTT:____");                        // connexion réussie
  } else {
    Serial.println("LIEN:MQTT:____");                        // connexion échouée
    Serial.print("# code MQTT : ");
    Serial.println(mqtt.state());                            // -2 : broker injoignable
  }
}

// Rappel régulier de l'état de la liaison, pour un PC qui se connecte en retard.
void rappelerEtat() {
  // TODO 5 : remplacer chaque ____
  if (WiFi.status() == ____) {                           // le Wi-Fi est connecté
    Serial.println("LIEN:WIFI:OK");
  }
  Serial.println(mqtt.____() ? "LIEN:MQTT:OK" : "LIEN:MQTT:ERREUR");   // méthode qui indique si MQTT est connecté
  if (etatAdversaire.length() > 0) {
    Serial.print("MSG:");
    Serial.print(____);                                  // le sous-topic de l'adversaire
    Serial.print("=");
    Serial.println(____);                                // son dernier état connu
  }
}

// ---------------------------------------------------------------- programme
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);                 // LED éteinte au démarrage

  base = "53A/jeu/" + String(EQUIPE) + "/";
  topicEtat = base + String(JOUEUR) + "/etat";
  sousTopicAdversaire = String(strcmp(JOUEUR, "j1") == 0 ? "j2" : "j1") + "/etat";

  WiFi.mode(WIFI_STA);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);          // antenne faible de certaines Super Mini
  WiFi.begin(WIFI_SSID, WIFI_MDP);             // ne bloque pas : on surveille l'état dans loop()
  mqtt.setServer(BROKER, PORT_MQTT);
  mqtt.setCallback(messageRecu);
  mqtt.setSocketTimeout(3);                    // une tentative de connexion échoue après 3 s au plus
}

void loop() {
  // Fourni : on annonce la connexion Wi-Fi une seule fois ; la carte se reconnecte
  // seule en cas de coupure.
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiAnnonce) {
      wifiAnnonce = true;
      Serial.println("LIEN:WIFI:OK");
    }
  } else {
    wifiAnnonce = false;
  }

  // TODO 6 : remplacer chaque ____

  // 1. Reconnexion MQTT, au plus toutes les 2 s, sans delay()
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()
      && millis() - ____ >= DELAI_RECONNEXION_MQTT) {    // l'instant du dernier essai
    ____ = millis();                                     // on note l'instant de cet essai
    connecterMqtt();
  }

  // 2. À appeler à CHAQUE tour : reçoit les messages (-> messageRecu) et entretient la connexion
  mqtt.____();

  // 3. Commandes du PC
  ____();                                                // la fonction qui lit le port série

  // 4. Rappel de l'état au PC, toutes les DELAI_RAPPEL_ETAT ms
  if (millis() - dernierRappel >= ____) {                // le délai entre deux rappels
    dernierRappel = ____;                                // l'instant actuel
    rappelerEtat();
  }
}
