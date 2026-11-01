# TTG+: queued continuations and compiler-emitted SQL

Five existing applications, six fixtures, 72 fresh workflows: 18 excluded warmups and54 measured trials (n = 3 in all 18 cells).
Primary DB metrics: actual PgWire sendall to ReadyForQuery protocol completion wall, summed intervals and their union, all-role SQL/data/control counts.

| Fixture | Mode | Protocol median ms | Range ms | TOTAL SQL | Data | Control |
|---|---|---:|---|---:|---:|---:|
|LinkedList · 32|Off (9282)|115.080873|113.694740–119.005918|360|318|42|
|LinkedList · 32|TTG+ 85026d|94.460859|94.298630–96.608904|243|196|47|
|LinkedList · 32|TTG+ 9282|94.370845|93.375101–94.836019|243|196|47|
|LinkedList · 1,000|Off (9282)|3337.873356|3147.031364–3387.414461|9072|9030|42|
|LinkedList · 1,000|TTG+ 85026d|2360.957330|2356.131173–2374.842955|5083|5036|47|
|LinkedList · 1,000|TTG+ 9282|2310.505553|2250.324724–2311.392378|5083|5036|47|
|LittleX|Off (9282)|42.578022|38.132471–43.135285|153|90|63|
|LittleX|TTG+ 85026d|55.479310|54.379551–56.864239|147|78|69|
|LittleX|TTG+ 9282|53.566271|51.472839–54.370708|151|82|69|
|IssueDesk|Off (9282)|139.439654|138.210529–142.840364|557|368|189|
|IssueDesk|TTG+ 85026d|154.267224|152.612606–157.883828|561|368|193|
|IssueDesk|TTG+ 9282|159.419406|157.615212–163.092390|561|368|193|
|KnowledgeMap|Off (9282)|72.712429|71.422240–73.790614|298|186|112|
|KnowledgeMap|TTG+ 85026d|78.996879|76.774249–84.613690|301|186|115|
|KnowledgeMap|TTG+ 9282|79.167199|79.033120–79.360169|301|186|115|
|JDrive|Off (9282)|48.053088|45.434338–48.143258|156|107|49|
|JDrive|TTG+ 85026d|46.783545|46.522596–47.213596|156|107|49|
|JDrive|TTG+ 9282|46.647880|45.127518–46.885064|156|107|49|

All 72 observed protocol sums equal unions. SQL includes all foreground/background and transaction-control calls.
The fixed application workloads observe one bound seed/demand origin per template query (not total recursive expansion); the four-origin native fixture is separate functional evidence.
Construction microbenchmark results, compiler initialization, full ranges and artifact growth are retained separately.
See figure-inputs.json for exact source/evidence references and complete statistics.
