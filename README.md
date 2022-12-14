# 2. úkol z KIV/DS

Úkol je rozšířením 1. úkolu (https://github.com/aitakaitov/ds-01), a tedy princip formování logického kruhu, volby leadera
a obarvování je v podstatě stejný.

Spuštění přes <code>vagrant up</code>, skript pro simulaci výpadku není, ale stačí vypnout kontejner. Pokud
by byl problém v bufferingu stdout, lze přepnout na výpis do souboru (viz. předchozí úloha).

## Výpadek a znovuobarvení

Když se kruh formuje, každý uzel má nastavený maximální počet pokusů o kontaktování svého počátačního souseda. Pokud
se ho nepodaří kontaktovat, přesune se na dalšího.

Každý uzel si při první odpovědi jeho souseda zaznamená jeho ID. Poté každých 30 vteřin posílá ping. Pokud sousední uzel na 
ping neodpoví, je považován za mrtvý. Poté se spustí následující sekvence akcí:

* Uzel pinguje další uzel v kruhu a čeká na odpověď - pokud uzel neodpoví, pinguje další uzel v kruhu a tento proces se
zastaví až pokud je v kruhu naživu jediný uzel, který se nastaví na leadera a obarví zeleně.
  
* Pokud existuje další uzel v kruhu, který funguje, nastaví ho jako nového souseda.

    * Pokud vypadl obyčejný uzel, posílá sousedovi zprávu NODE DOWN, která se dostane k leaderovi.
    * Ten pak znovu posílá COLLECT zprávu a pak COLOR zprávu. Tím se znovu obarví všechny uzly.
    * To řeší i situaci, kdy vypadne více uzlů a některé 
      NODE DOWN zprávy se nedostanou k leaderovi - když se opraví poslední spojení mezi uzlem a sousedem, tak je kruh kompletní
      a daná NODE DOWN zpráva se k leaderovi dostane. Pak se posbírají ID a provede obarvení.
  
* Pokud vypadl leader, situace je komplikovanější. 
    * Uzel nastavuje časovač, který periodicky posílá LEADER DOWN zprávu.
    * Ta se propaguje ke všem uzlům v kruhu, čímž se všechny připraví na novou volbu leadera. Uzel zastaví časovač když se
      mu odeslaná LEADER DOWN zpráva vrátí - kruh je kompletní a všichni ví, že není leader.
    * Pak nastavuje časovač pro odesílání ELECTION zpráv - když uzel dostane ELECTION zprávu a blokuje ji, odešle vlastní ELECTION zprávu.  
    * Poté volba leadera a obarvování pokračuje standardním způsobem.

Tento přístup řeší i případy typu výpadek několika po sobě jdoucích uzlů kde leader je první z nich (po směru hodinových ručiček),
několika po sobě jdoucích uzlů bez leadera, několika ne-po-sobě-jdoucích uzlů (i leadera), a výpadek jednotlivých uzlů. 
  
Některé zprávy se posílají asynchronně - requests nepodporuje neblokující požadavky, takže se u některých zpráv stalo,
že se metoda (volaná časovačem, většinou) dokončila až poté, co se požadavek vrátil zpět k odesílateli, což nebylo úplně praktické.

## Omezení

* Pokud uzel obnoví svou činnost, už nemůže být začleněn zpět do kruhu.

* Pokud dojde k výpadku více po sobě jdoucích uzlů a jiný než první z nich je leader - uzel nemá jak zjistit, jaká je pozice
leadera v kruhu pokud není jeho pravým sousedem. Tím pádem se po rekonstrukci kruhu nezvolí nový leader. To lze vyřešit tím,
  že každý uzel periodicky pošle dotaz na existenci leadera - pokud je v kruhu leader, tak bude nastaven příznak a uzel
  může odchytit zprávu, kterou sám vyslal.
  
* Pokud dojde k výpadku v procesu volby leadera, volba leadera se nemusí dokončit.
  
## Poznámky

* Aplikace může vypisovat výjimky do STDOUT, protože /message není obalená try-except blokem. Flask si interně s výjimkou 
poradí, takže aplikace nespadne. Jediný mechanismus pro detekci výpadků je pingování.

* Kód není úplně nejčistší, snažil jsem se všechno dostatečně okomentovat.

## Seznam testů

* Výpadek ne-leader uzlu po obarvení 
    * OK
* Výpadek uzlu před zformováním kruhu (jeden node nenastartován)
    * OK
* Výpadek leadera
    * OK
* Výpadek dvou uzlů
    * OK
* Výpadek dvou uzlů za sebou
    * OK
* Výpadek leadera a dalšího uzlu
    * OK
* Výpadek leadera a následujícího uzlu
    * OK