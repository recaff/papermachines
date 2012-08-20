#!/usr/bin/env python
import sys, os, json, logging, traceback, base64, time, codecs
import cPickle as pickle
from lib.placemaker import placemaker
from lib.placemaker.placemaker_api import placemaker_api_key
import textprocessor


class Geoparse(textprocessor.TextProcessor):
	"""
	Geoparsing using Yahoo! Placemaker
	"""

	def _basic_params(self):
		self.name = "geoparse"
		self.dry_run = False

	def process(self):
		"""
		create a JSON file with geographical data extracted from texts
		"""

		self.name = "geoparse"

		p = placemaker(base64.b64decode(placemaker_api_key))

		geo_parsed = {}
		places_by_woeid = {}
		origins_by_filename = {}
		out_filename = os.path.join(self.out_dir, self.name + self.collection + '.json')

		if not self.dry_run:
			output = file(out_filename, 'w')
			for filename in self.files:
				logging.info("processing " + filename)
				self.update_progress()
				try:
					# id = self.metadata[filename]['itemID']
					str_to_parse = self.metadata[filename]['place']
					last_index = len(str_to_parse)
					str_to_parse += codecs.open(filename, 'r', encoding='utf8').read()[0:(48000 - last_index)] #50k characters, shortened by initial place string

					city = None
					places = []
					
					p.find_places(str_to_parse.encode('utf8', 'ignore'))
					for woeid, referenced_place in p.referencedPlaces.iteritems():
						place = referenced_place["place"]
						places_by_woeid[woeid] = {'name': place.name, 'type': place.placetype, 'coordinates': [place.centroid.longitude, place.centroid.latitude]}

						for reference in referenced_place["references"]:
							if reference.start < last_index:
								city = woeid
							else:
								places.append(woeid)

					geo_parsed[filename] = places
					if city is not None:
						self.metadata[filename]['city'] = city
						origins_by_filename[filename] = city
					time.sleep(0.2)
				except (KeyboardInterrupt, SystemExit):
					raise
				except:
					logging.error(traceback.format_exc())

			json.dump([places_by_woeid, geo_parsed, origins_by_filename], output)
			output.close()
		elif os.path.exists(out_filename):
			(places_by_woeid, geo_parsed, origins_by_filename) = json.load(file(out_filename))

		data_filename = os.path.join(self.out_dir, self.name + self.collection + '.js')

		places = {}
		for filename, woeids in geo_parsed.iteritems():
			year = self.metadata[filename]["year"]
			for woeid in woeids:
				if woeid not in places:
					places[woeid] = {}
					places[woeid]["name"] = places_by_woeid[woeid]["name"]
					places[woeid]["type"] = places_by_woeid[woeid]["type"]
					places[woeid]["coordinates"] = places_by_woeid[woeid]["coordinates"]
					places[woeid]["weight"] = {year: 1}
				else:
					if year not in places[woeid]["weight"]:
						places[woeid]["weight"][year] = 1
					else:
						places[woeid]["weight"][year] += 1

		max_country_weight = 0

		for place in sorted(places.keys()):
			if places[place]["type"] == "Country":
				country_sum = sum(places[place]["weight"].values())
				if country_sum > max_country_weight:
					max_country_weight = country_sum

		placeIDsToNames = {k: v["name"] for k, v in places_by_woeid.iteritems()}
		placeIDsToCoords = {k: v["coordinates"] for k, v in places_by_woeid.iteritems()}

		linksByYear = {}
		for filename in self.files:
			if not 'city' in self.metadata[filename] or len(geo_parsed[filename]) < 2:
				continue
			try:
				title = os.path.basename(filename)
				itemID = self.metadata[filename]['itemID']
				year = self.metadata[filename]['year']
				if year not in linksByYear:
					linksByYear[year] = {}
				source = self.metadata[filename]['city']
				targets = geo_parsed[filename]
				for target in targets:
					edge = str(source) + ',' + str(target)
					if edge not in linksByYear[year]:
						linksByYear[year][edge] = 1
					else:
						linksByYear[year][edge] += 1
			except:
				logging.info(traceback.format_exc())

		years = sorted(linksByYear.keys())
		groupedLinksByYear = []

		for year in years:
			groupedLinksByYear.append([])
			for edge in linksByYear[year]:
				weight = linksByYear[year][edge]
				source, target = [int(x) for x in edge.split(',')]
				groupedLinksByYear[-1].append({'source': source, 'target': target, 'year': year, 'weight': weight})


		data_vars = {"placeIDsToCoords": placeIDsToCoords,
			"placeIDsToNames": placeIDsToNames,
			"placesMentioned": {v["name"] : v["weight"] for k, v in places.iteritems() if v["type"] != "Country"},
			"countries": {v["name"] : v["weight"] for k, v in places.iteritems() if v["type"] == "Country"},
			"max_country_weight": max_country_weight,
			"startDate": min([int(x["year"]) for x in self.metadata.values() if x["year"].isdigit()]),
			"endDate": max([int(x["year"]) for x in self.metadata.values() if x["year"].isdigit()])
		}

		data = ""

		for k, v in data_vars.iteritems():
			data += "var "+ k + "=" + json.dumps(v) + ";\n";

		logging.info("writing JS include file")

		with file(data_filename, 'w') as data_file:
			data_file.write(data)

		params = {"DATA_FILE": os.path.basename(data_filename), "LINKS_BY_YEAR": json.dumps(groupedLinksByYear)}
		self.write_html(params)

		logging.info("finished")


if __name__ == "__main__":
	try:
		processor = Geoparse(track_progress=True)
		processor.process()
	except:
		logging.error(traceback.format_exc())