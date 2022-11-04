# 2. úkol z KIV/DS

Úkol je rozšířením 1. úkolu (https://github.com/aitakaitov/ds-01), a tedy princip formování logického kruhu, volby leadera
a obarvování je v podstatě stejný.

## Výpadek a znovuobarvení

Každý uzel si při první odpovědi jeho souseda zaznamená jeho ID. Poté každých 60 vteřin posílá ping. Pokud soused na 
ping neodpoví, je považován za mrtvý. Poté se spustí následující sekvence akcí:

* Uzel pinguje další uzel v kruhu a čeká na odpověď - pokud uzel neodpoví, pinguje další uzel v kruhu a tento proces se
zastaví až pokud je v kruhu naživu jediný uzel, který se nastaví na leadera a obarví zeleně.
  
* Pokud existuje další uzel v kruhu, který funguje, nastaví ho jako nového souseda.

* Pokud vypadl obyčejný uzel, posílá sousedovi zprávu NODE DOWN, která se dostane k leaderovi. Ten pak znovu posílá
COLLECT zprávu a pak COLOR zprávu. Tím se znovu obarví všechny uzly. To řeší i situaci, kdy vypadne více uzlů a některé 
  NODE DOWN zprávy se nedostanou k leaderovi - když se opraví poslední spojení mezi uzlem a sousedem, tak je kruh kompletní
  a daná NODE DOWN zpráva se k leaderovi dostane.
  
* Pokud vypadl leader, uzel posílá sousedovi zprávu LEADER DOWN. Ta se propaguje ke všem uzlům v kruhu, čímž se všechny 
  připraví na novou volbu leadera. Uzel pak nastavuje opakující se odesílání ELECTION zprávy - to kvůli tomu, že 
  je nutné zaručit, že se LEADER DOWN zpráva dostane ke všem uzlům před tím, než dostanou ELECTION zprávu. Uzly ELECTION
  zprávy ignorují, pokud nemají informaci o tom, že leader nefunguje - opakováním zprávy řešíme situaci, kdy by ELECTION
  zpráva došla dřív, než LEADER DOWN.
  
* Volba leadera pak pokračuje jako při inicializaci.

## Omezení

* Pokud uzel obnoví svou činnost, už nemůže být začleněn zpět do kruhu.

* Pokud dojde k výpadku více po sobě jdoucích uzlů a jiný než první z nich je leader - uzel nemá jak zjistit, jaká je pozice
leadera v kruhu pokud není jeho pravým sousedem. Tím pádem se po rekonstrukci kruhu nezvolí nový leader. To lze vyřešit tím,
  že každý uzel periodicky pošle dotaz na existenci leadera - pokud je v kruhu leader, tak bude nastaven příznak a uzel
  může odchytit zprávu, kterou sám vyslal.
  
* Pokud dojde k výpadku v procesu volby leadera, volba leadera se nedokončí.
  
## Poznámky

* Aplikace může vypisovat výjimky do STDOUT, protože /message není obalená try-except blokem. Flask si interně s výjimkou 
poradí, takže aplikace nespadne. Jediný mechanismus pro detekci výpadků je pingování.
  
* Při výpadku leadera se používají timery pro odesílání LEADER DOWN zpráv, ale z nějakého důvodu (asi nějaká kryptická
  pythoní záležitost) se může stát, že se jako funkce timeru zavolá None, i když v kódu k tomu nevidím důvod. Nepozoroval
  jsem žádný efekt mimo výpis výjimky.

## Seznam testů

* Výpadek ne-leader uzlu po obarvení 
    * OK
* Výpadek uzlu před zformováním kruhu (jeden node nenastartován)
    * OK
* Výpadek leadera
    * OK
* Výpadek dvou uzlů v krátkém sledu
    * OK
* Výpadek dvou uzlů za sebou v krátkém sledu
    * OK
* Výpadek leadera a dalšího uzlu v krátkém sledu
    * OK
* Výpadek leadera a následujícího uzlu v krátkém sledu
    * OK