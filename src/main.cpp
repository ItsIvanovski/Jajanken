#include <Arduino.h>        // fonctions de base : pinMode, digitalWrite, millis...
#include <WiFi.h>           // connexion au réseau Wi-Fi de l'ESP32
#include <PubSubClient.h>   // client MQTT (publier, s'abonner)
/*
  243-53A-MO — Interface usager de microcontrôleurs — Projet 1

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

  Attention : le port série sert de canal de protocole. Tout Serial.println()
  de débogage doit commencer par # pour être ignoré par l'interface.

  Programmeur : Guillaume Beaulieu (code troué), complété par l'équipe
  Date de création : 2026-10-22
  Dernière modification : 2026-11-04
*/

// ---------------------------------------------------------------- réglages
// À adapter : votre équipe, votre joueur et votre local
const char* EQUIPE = "equipe1";              // nom court, sans espace, UNIQUE dans la classe (même valeur que dans l'interface)
const char* JOUEUR = "j1";                   // "j1" ou "j2" (j2 sur la carte du coéquipier)

const char* WIFI_SSID = "TGE-C3521";         // Local C-3521
// const char* WIFI_SSID = "TGE-C3516";      // Local C-3516
const char* WIFI_MDP  = "Tge2026++";         // même mot de passe dans les deux locaux

const char* BROKER    = "10.35.21.5";        // Local C-3521 (Raspberry Pi)
// const char* BROKER = "10.35.16.5";        // Local C-3516 (Raspberry Pi)
const int   PORT_MQTT = 1883;

const int PIN_LED = 8;                       // LED bleue intégrée (logique inversée : LOW = allumée)
#define LED_ALLUMEE LOW                      // logique inversée sur l'ESP32-C3 Super Mini
#define LED_ETEINTE HIGH

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
  // TODO 1 : relayer un message MQTT reçu vers le PC (ligne MSG:)
  String texte;
  for (unsigned int i = 0; i < longueur; i++) {          // payload n'est PAS terminé par \0 : on utilise sa longueur
    texte += (char)payload[i];
  }
  String sousTopic = String(topic).substring(base.length());   // retire le préfixe « base » (ex. « coup », « j2/etat »)
  if (sousTopic == sousTopicAdversaire) {                // c'est l'état de l'adversaire : on le garde pour le rappel
    etatAdversaire = texte;
  }
  Serial.print("MSG:");
  Serial.print(sousTopic);                               // le sous-topic
  Serial.print("=");
  Serial.println(texte);                                 // le texte du message
}

// ---------------------------------------------------------------- commandes du PC
// Exécute une ligne complète (sans le \n) reçue du PC.
void traiterLigne(String ligne) {
  // TODO 2 : exécuter une commande du PC (PUB: et LED:)
  ligne.trim();                                          // enlève les espaces et le \r aux extrémités
  if (ligne.length() == 0) return;

  if (ligne.startsWith("PUB:")) {                        // la commande de publication « PUB: »
    String reste = ligne.substring(4);                   // ce qui suit « PUB: » (4 caractères)
    int egal = reste.indexOf('=');                       // position du PREMIER caractère « = »
    if (egal < 1) {                                      // pas de « = », ou sous-topic vide
      Serial.println("# PUB mal formée");
      return;
    }
    String sousTopic = reste.substring(0, egal);         // tout ce qui précède le « = »
    String message = reste.substring(egal + 1);          // tout ce qui suit le « = »
    if (mqtt.connected()) {
      mqtt.publish((base + sousTopic).c_str(), message.c_str());   // publie sur 53A/jeu/<EQUIPE>/<sous-topic>
    } else {
      Serial.println("# MQTT non connecté : message perdu");
    }
    return;
  }

  if (ligne == "LED:ON") {
    digitalWrite(PIN_LED, LED_ALLUMEE);                  // logique inversée : LOW = allumée
  } else if (ligne == "LED:OFF") {
    digitalWrite(PIN_LED, LED_ETEINTE);                  // HIGH = éteinte
  } else {
    Serial.println("# commande inconnue");
  }
}

// Lit les octets disponibles sans jamais attendre.
// (Contrairement à readStringUntil() du labo 4, on ne bloque jamais : on accumule
//  les caractères dans ligneSerie jusqu'au \n.)
void lireSerie() {
  // TODO 3 : lire le port série sans bloquer, ligne par ligne
  while (Serial.available() > 0) {                      // il reste des octets à lire
    char c = Serial.read();                              // lit UN octet
    if (c == '\n') {                                     // fin de ligne : la commande est complète
      traiterLigne(ligneSerie);
      ligneSerie = "";
    } else if (c != '\r') {
      ligneSerie += c;
    }
  }
}

// ---------------------------------------------------------------- MQTT
void connecterMqtt() {
  // TODO 4 : connexion au broker avec testament, état « en ligne », abonnement
  // Identifiant unique : deux clients avec le même identifiant s'éjectent
  String id = "esp32c3-" + String(JOUEUR) + "-" + WiFi.macAddress();

  // connect(identifiant, topicTestament, qos, retenu, messageTestament)
  // Les quatre derniers arguments sont le TESTAMENT : si la carte disparaît sans se
  // déconnecter, le broker publie « hors ligne » à sa place.
  if (mqtt.connect(id.c_str(), topicEtat.c_str(), 0, true, "hors ligne")) {   // testament retenu
    mqtt.publish(topicEtat.c_str(), "en ligne", true);       // « en ligne », en message retenu
    mqtt.subscribe((base + "#").c_str());                    // tous les sous-topics de l'équipe (joker #)
    Serial.println("LIEN:MQTT:OK");                          // connexion réussie
  } else {
    Serial.println("LIEN:MQTT:ERREUR");                      // connexion échouée
    Serial.print("# code MQTT : ");
    Serial.println(mqtt.state());                            // -2 : broker injoignable
  }
}

// Rappel régulier de l'état de la liaison, pour un PC qui se connecte en retard.
void rappelerEtat() {
  // TODO 5 : répéter l'état de la liaison et celui de l'adversaire
  if (WiFi.status() == WL_CONNECTED) {                   // le Wi-Fi est connecté
    Serial.println("LIEN:WIFI:OK");
  }
  Serial.println(mqtt.connected() ? "LIEN:MQTT:OK" : "LIEN:MQTT:ERREUR");
  if (etatAdversaire.length() > 0) {
    Serial.print("MSG:");
    Serial.print(sousTopicAdversaire);                   // le sous-topic de l'adversaire
    Serial.print("=");
    Serial.println(etatAdversaire);                      // son dernier état connu
  }
}

// ---------------------------------------------------------------- programme
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LED_ETEINTE);          // LED éteinte au démarrage

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
  // On annonce la connexion Wi-Fi une seule fois ; la carte se reconnecte
  // seule en cas de coupure.
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiAnnonce) {
      wifiAnnonce = true;
      Serial.println("LIEN:WIFI:OK");
    }
  } else {
    wifiAnnonce = false;
  }

  // TODO 6 : reconnexion MQTT, mqtt.loop(), lecture série, rappel périodique

  // 1. Reconnexion MQTT, au plus toutes les 2 s, sans delay()
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()
      && millis() - dernierEssaiMqtt >= DELAI_RECONNEXION_MQTT) {
    dernierEssaiMqtt = millis();                         // on note l'instant de cet essai
    connecterMqtt();
  }

  // 2. À appeler à CHAQUE tour : reçoit les messages (-> messageRecu) et entretient la connexion
  mqtt.loop();

  // 3. Commandes du PC
  lireSerie();

  // 4. Rappel de l'état au PC, toutes les DELAI_RAPPEL_ETAT ms (même principe que le labo 4)
  if (millis() - dernierRappel >= DELAI_RAPPEL_ETAT) {
    dernierRappel = millis();                            // l'instant actuel
    rappelerEtat();
  }
}