from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

class Itineraire:

    def __init__(self, uri, user, password):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        self._driver.close()
            
    def init_db(self):
        with self._driver.session(database='neo4j') as session:
            try:
                    # Check and initialize nodes
                    session.execute_write(self.create_nodes)

                    # Check and initialize station relationships
                    session.execute_write(self.create_station_relationships)

                    # Check and initialize correspondence relationships
                    session.execute_write(self.create_correspondence_relationships)

                    # Check and initialize walking relationships
                    session.execute_write(self.create_walking_relationships)
                    
                    # Check if distances have been calculated
                    session.execute_write(self.calculate_distances)
                    
                    # Check if travel times have been calculated
                    session.execute_write(self.calculate_travel_times)

                    # Check if named graph exists
                    session.execute_write(self.create_named_graph)

            except Neo4jError as ne:
                print(f"Neo4j Error: {ne}")

            except Exception as e:
                print(f"General Error: {e}")
            
 
    def create_nodes(self, session):    
            # Vérifier si des noeuds existent déjà
            if not session.run("MATCH (s:Station) RETURN s LIMIT 1").single():
                # Étape 1: Création des nœuds pour les stations
                session.run("LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/pauldechorgnat/cool-datasets/master/ratp/stations.csv' AS row "
                            "CREATE (s:Station { "
                            "name: row.nom_clean, "
                            "line: toInteger(row.ligne), "
                            "lat: toFloat(row.x), "
                            "lon: toFloat(row.y), "
                            "nom_gare: row.nom_gare, "
                            "traffic: toInteger(row.Trafic), "
                            "city: row.Ville "
                            "});")
                print("Nodes created successfully.")
            else:
                print("Les nœuds de station existent déjà.")


    def create_station_relationships(self, session):
            # Vérifier si des relations entre les stations existent déjà
            if not session.run("MATCH ()-[:CONNECTS_TO]->() RETURN 1 LIMIT 1").single():
                # Étape 2: Création des relations entre stations de la même ligne
                session.run("LOAD CSV WITH HEADERS FROM 'https://raw.githubusercontent.com/pauldechorgnat/cool-datasets/master/ratp/liaisons.csv' AS row "
                            "MATCH (start:Station {name: row.start}), (stop:Station {name: row.stop}) "
                            "WHERE start.line = toInteger(row.ligne) AND stop.line = toInteger(row.ligne) "
                            "MERGE (start)-[:CONNECTS_TO {mode: 'train', speed: 2000/3}]->(stop);")
                print("Station relationships created successfully.")
            else:
                print("Les relations de station existent déjà.")
    

    def create_correspondence_relationships(self, session):
            # Vérifier si des relations de correspondance existent déjà
            if not session.run("MATCH ()-[:CORRESPONDENCE]->() RETURN 1 LIMIT 1").single():
                # Étape 3: Création des relations de correspondance entre les lignes d'une même station
                session.run("MATCH (s1:Station), (s2:Station) "
                            "WHERE s1.name = s2.name AND s1.line <> s2.line "
                            "MERGE (s1)-[:CORRESPONDENCE {time: 4}]->(s2);")
                print("Correspondence relationships created successfully.")
            else:
                print("Les relations de correspondance existent déjà.")


    def create_walking_relationships(self, session):
        # Vérifier si des relations pour les déplacements à pied existent déjà
        if not session.run("MATCH ()-[:WALK_TO]->() RETURN 1 LIMIT 1").single():
            # Étape 4: Création des relations pour les déplacements à pied
            session.run("MATCH (s1:Station), (s2:Station) "
                        "WHERE s1 <> s2 AND SQRT((s1.lat - s2.lat)^2 + (s1.lon - s2.lon)^2) < 1000 "
                        "MERGE (s1)-[:WALK_TO {speed: 200/3}]->(s2);")
            print("Walking relationships created successfully.")
        else:
            print("Les relations pour les déplacements à pied existent déjà.")
   

    def calculate_distances(self, session):
        if not session.run("MATCH ()-[r:CONNECTS_TO]-() WHERE r.distance IS NOT NULL RETURN 1 LIMIT 1").single() and \
           not session.run("MATCH ()-[r:WALK_TO]-() WHERE r.distance IS NOT NULL RETURN 1 LIMIT 1").single():
            session.run("MATCH (s1:Station)-[r:CONNECTS_TO]->(s2:Station) "
                        "WITH s1, s2, r, SQRT((s1.lat - s2.lat)^2 + (s1.lon - s2.lon)^2) as distance "
                        "SET r.distance = distance")
            
            session.run("MATCH (s1:Station)-[r:WALK_TO]->(s2:Station) "
                        "WITH s1, s2, r, SQRT((s1.lat - s2.lat)^2 + (s1.lon - s2.lon)^2) as distance "
                        "SET r.distance = distance")  

            print("Distances calculated successfully.")
        else:
            print("Les propriétés distances existent déjà.")

    def calculate_travel_times(self, session):
        if not session.run("MATCH ()-[r:CONNECTS_TO]-() WHERE r.time IS NOT NULL RETURN 1 LIMIT 1").single() and \
           not session.run("MATCH ()-[r:WALK_TO]-() WHERE r.time IS NOT NULL RETURN 1 LIMIT 1").single():
            # Étape 5:       
            session.run("MATCH (s1:Station)-[r:CONNECTS_TO]->(s2:Station) "
                        "WITH s1, s2, r, r.distance as distance "
                        "SET r.time = distance / r.speed ")
            
            session.run("MATCH (s1:Station)-[r:WALK_TO]->(s2:Station) "
                        "WITH s1, s2, r, r.distance as distance "
                        "SET r.time = distance / r.speed ")
            print("Travel times calculated successfully.")
        else:
            print("Les propriétés time existent déjà.")
    
    def create_named_graph(self, session):
        with self._driver.session(database='neo4j') as session:
            exists_check = session.run("CALL gds.graph.exists('dst') YIELD exists RETURN exists").single()
            if exists_check and exists_check['exists']:
                print("The graph dst exists and will be deleted.")
                session.run("CALL gds.graph.drop('dst')")
                print("The previous graph was deleted.")
                
            print("The graph dst will be created.")
            # Création du graphe nommé
            session.run("""
                CALL gds.graph.project(
                    'dst', 
                    {
                        Station: {
                            label: 'Station',
                            properties: {
                                line: 'line',
                                lat: 'lat',
                                lon: 'lon',
                                traffic: 'traffic'
                            }
                        }
                    },
                    {
                        CONNECTS_TO: {
                            type: 'CONNECTS_TO',
                            properties: {
                                speed: 'speed',
                                distance: 'distance',
                                time: 'time'
                            }
                        },
                        CORRESPONDENCE: {
                            type: 'CORRESPONDENCE',
                            properties: {
                                time: 'time'
                            }
                        },
                        WALK_TO: {
                            type: 'WALK_TO',
                            properties: {
                                speed: 'speed',
                                distance: 'distance',
                                time: 'time'
                            }
                        }
                    }
                )
            """)
            print("The graph dst was created successfully.")
            
    def get_station_name_from_coordinates(self, x, y):
        with self._driver.session(database='neo4j') as session:
            query = (
                "MATCH (s:Station) "
                "RETURN s.name AS name, SQRT((s.lat - $x)^2 + (s.lon - $y)^2) AS distance "
                "ORDER BY distance ASC "
                "LIMIT 1"
            )
            result = session.run(query, x=x, y=y).single()
            return result["name"] if result else None            
        
    def get_shortest_path(self, start_station, end_station):
        with self._driver.session(database='neo4j') as session:
            query = (
                "MATCH (start:Station {name: $start_station}), (end:Station {name: $end_station}) "
                "CALL gds.shortestPath.dijkstra.stream('dst', {"
                "    sourceNode: start,"
                "    targetNode: end,"
                "    relationshipWeightProperty: 'time'"
                "})"
                "YIELD nodeIds, totalCost "
                "UNWIND range(0, size(nodeIds) - 2) AS idx "
                "WITH idx, gds.util.asNode(nodeIds[idx]) AS s, totalCost "
                "WITH s.name as Station, COLLECT(DISTINCT s.line) as Lines, totalCost "
                "RETURN Station, Lines, totalCost as TotalMinutes "
                "ORDER BY TotalMinutes;"
            )
            results = session.run(query, start_station=start_station, end_station=end_station)
            return [(record["Station"], record["Lines"], record["TotalMinutes"]) for record in results]


class ItineraireApp:
    def __init__(self):
        self.itineraire = Itineraire("neo4j://localhost:7687", "neo4j", "password")  # Remplacez par vos informations d'authentification

    def initialize_database(self):
        self.itineraire.init_db()

    def get_station_by_coordinates(self, i):
        x = float(input(f"Entrez la coordonnée x de la station {i + 1}: "))
        y = float(input(f"Entrez la coordonnée y de la station {i + 1}: "))

        station_name = self.itineraire.get_station_name_from_coordinates(x, y)
        if station_name:
            print(f"La station la plus proche pour la coordonnée {i + 1} est : {station_name}")
            return station_name
        else:
            print(f"Aucune station trouvée pour les coordonnées de la station {i + 1}.")
            return None

    def find_shortest_path(self, start_station, end_station):
        if start_station and end_station:
            shortest_path = self.itineraire.get_shortest_path(start_station, end_station)
            for station, lines, minutes in shortest_path:
                print(f"Station: {station}, Lignes: {', '.join(map(str, lines))}, TotalMinutes: {minutes}")

    def run(self):
        try:
            self.initialize_database()

            while True:  # Boucle principale
                stations = [self.get_station_by_coordinates(i) for i in range(2)]
                self.find_shortest_path(stations[0], stations[1])
                
                # Demander à l'utilisateur s'il souhaite continuer ou quitter
                choice = input("Voulez-vous entrer de nouvelles coordonnées? (Oui/Non): ").lower().strip()
                if choice == 'non':
                    break

        except Neo4jError as ne:
            print(f"Erreur Neo4j : {ne}")
        except Exception as e:
            print(f"Erreur générale : {e}")
            
        finally:
            self.itineraire.close()


if __name__ == "__main__":
    app = ItineraireApp()
    app.run()
