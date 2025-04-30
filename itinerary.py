import sys
from neo4j import GraphDatabase
from math import sqrt

print("there is still an issue with walking distance between start coordinates and first station and end coords and last station. \n It searches for all stations in a 600m radius around coordinates and searches best paths between all those stations. 10 start stations and 9 end stations = 90 pairs on which the fastest path has to be searched. 1 path remains.")

# Walking speed in meters per minute (4 km/h)
WALKING_SPEED = 4 * 1000 / 60  # 4000 meters per hour, converted to meters per minute

class MetroItinerary:
	def __init__(self, uri, user, password):
		self.driver = GraphDatabase.driver(uri, auth=(user, password))

	def close(self):
		self.driver.close()

	def calculate_walking_time(self, start_coords, end_coords):
		# Calculate walking time in minutes using the Euclidean distance in meters
		distance = self.calculate_distance(start_coords, end_coords)
		return distance / WALKING_SPEED  # Return time in minutes

	def calculate_distance(self, start_coords, end_coords):
		# Calculate the Euclidean distance between two points (x, y) in meters
		x1, y1 = start_coords
		x2, y2 = end_coords
		return sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

	def find_stations_within_radius(self, coords, radius):
		# Find stations within a given radius in meters from the coordinates
		x, y = coords
		with self.driver.session() as session:
			query = '''
			MATCH (s:Station)
			WHERE distance(s.location, point({x: $x, y: $y, crs: 'cartesian'})) < $radius
			RETURN s.name_clean AS name, s.location AS location
			'''
			result = session.run(query, x=x, y=y, radius=radius)
			stations = [(record['name'], record['location']) for record in result]
			print(f"Found {len(stations)} stations within {radius} meters of {coords}")
			return stations

	def calculate_fastest_route(self, start_coordinates, end_coordinates):
		# Get stations within 600m of the start and end coordinates
		start_stations = self.find_stations_within_radius(start_coordinates, 600)
		end_stations = self.find_stations_within_radius(end_coordinates, 600)

		if not start_stations or not end_stations:
			print("No stations found within 600 meters of the provided coordinates.")
			return None, None

		best_route = None
		best_time = float('inf')

		# Check all combinations of start and end stations
		for start_station_name, start_station_coords in start_stations:
			for end_station_name, end_station_coords in end_stations:
				# Calculate walking times to/from the stations
				walking_time_start = self.calculate_walking_time(start_coordinates, start_station_coords)
				walking_time_end = self.calculate_walking_time(end_coordinates, end_station_coords)

				# Find the shortest path between the start and end station
				with self.driver.session() as session:
					query = '''
					MATCH (start:Station {name_clean: $start_station}), 
						  (end:Station {name_clean: $end_station})
					CALL gds.alpha.shortestPath.stream({
						nodeQuery: 'MATCH (n:Station) RETURN id(n) AS id',
						relationshipQuery: 'MATCH (n1)-[rel]->(n2) WHERE type(rel) IN ["LIAISON", "CORRESPONDANCE"] RETURN id(rel) AS id, id(n1) AS source, id(n2) AS target, rel.weight AS weight',
						startNode: start,
						endNode: end,
						relationshipWeightProperty: 'weight'
					})
					YIELD nodeId, cost
					RETURN gds.util.asNode(nodeId) AS station, cost*60 AS travel_time
					ORDER BY travel_time
					'''
					result = session.run(query, start_station=start_station_name, end_station=end_station_name)
					path = []
					total_cost = 0

					# Collect the full path along with travel times and relationship weights
					for record in result:
						station = record['station']
						travel_time = record['travel_time']

						# To find the relationship weight, we need to query the connections
						relationship_query = '''
						MATCH (n1)-[r]->(n2)
						WHERE id(n1) = $start_station_id AND id(n2) = $end_station_id
						RETURN r.weight AS weight
						'''
						rel_result = session.run(relationship_query, 
												 start_station_id=station.element_id, 
												 end_station_id=station.element_id)  # Adjust if needed to find correct relation
						rel_weight = rel_result.single()['weight'] if rel_result.single() else 0

						# Add station info to the path (without coordinates and weight display if not needed)
						path.append(f"Station: {station['name_clean']}, Line: {station['line']}, Travel Time: {travel_time:.2f} mins")
						total_cost += travel_time

					# Calculate total time: walking time + metro travel time
					total_time = walking_time_start + walking_time_end + total_cost

					# Keep track of the best route with the shortest total time
					if total_time < best_time:
						best_time = total_time
						best_route = path

		return best_route, best_time

if __name__ == "__main__":
	# Ensure correct number of command-line arguments
	if len(sys.argv) != 5:
		print("Usage: python itinerary.py <start_x> <start_y> <end_x> <end_y>")
		sys.exit(1)

	# Parse command-line arguments for coordinates
	start_x = float(sys.argv[1])
	start_y = float(sys.argv[2])
	end_x = float(sys.argv[3])
	end_y = float(sys.argv[4])

	start_coordinates = (start_x, start_y)
	end_coordinates = (end_x, end_y)

	# Neo4j connection credentials
	uri = "bolt://localhost:7687"
	user = "neo4j"
	password = "neo4j"

	itinerary_calculator = MetroItinerary(uri, user, password)
	try:
		# Get the best route
		best_route, total_time = itinerary_calculator.calculate_fastest_route(start_coordinates, end_coordinates)

		if best_route:
			print("Best Route:")
			for station_info in best_route:
				print(station_info)

			print(f"Total Travel Time: {total_time:.2f} minutes")
		else:
			print("No path found.")
	finally:
		itinerary_calculator.close()
