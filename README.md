## What this is trying to solve

An Indian buyer imports dry bulk cargo, chiefly coal, from Australia, the United States, Mozambique, Russia and Indonesia into ports on India's East Coast. Today they hire ships one voyage at a time, checking the freight market daily and taking whatever the rate happens to be. That is reactive. Freight rates swing hard, so buying this way means missing the cheap windows and getting caught in the expensive ones.

There is a second, quieter cost. The East Coast ports are not interchangeable. Each has its own depth, length and berth limits. Pick a ship that is too big for the destination and it either waits for a tide, or has to offload part of its cargo into barges before it can dock. Both cost real money, and neither shows up in the freight rate you agreed.

The brief's stated objective is one sentence: move from many single spot contracts to short and medium term multi-voyage contracts. So the tool has one commercial job. Forecast where freight rates are going, then use that forecast to answer three questions. When should we enter the market, which size of ship should we take given where we are discharging, and should we lock a multi-voyage contract or keep buying voyage by voyage.

The last question is the one the contract simulator now answers in rupees.

## What is in the codebase

Six pages behind a sidebar. The **Command Center** is the home dashboard, currently all hardcoded. The **Route Map** draws the loading and discharge ports on a Leaflet map, coloured by whether the selected ship class can enter. The **Forecast** page plots historical rates against a predicted curve with a confidence band, per ship class, over one, three and six months. The **Vessel Matcher** takes a cargo size and a destination and ranks the four ship classes as available, constrained or blocked. The **Contract Simulator** is the spot against multi-voyage comparison. **Risk & Alerts** is a stub.

Underneath, four data files describe the world. Ports carry their depth, length limit, berth count, discharge speed and congestion level. Vessels carry the dimensions and speed of each size class. The forecast file generates the rate series. The cost assumptions file holds every price the costing model uses, in one place, so a commercial person can argue with the numbers without reading code.

The engine added in this session takes a programme of voyages and prices it twice, once at forecast spot rates and once at a locked rate, then reports the difference, the rate at which the two break even, and how likely the forecast is to be wrong enough to flip the answer.

## The vocabulary

**The commercial terms, which is most of it**

| Term | What it means |
|---|---|
| Charter | Hiring a ship. The owner owns it, the charterer hires it. |
| Charterer | Here, the Indian buyer hiring ships to bring coal in. |
| Fixture | A concluded charter deal. To "fix" a ship is to agree one. |
| Spot | Hiring for a single voyage at today's market rate. |
| Voyage charter | Owner carries cargo from A to B for a rate per tonne and pays the crew, fuel and port costs out of it. |
| CVC, Consecutive Voyage Charter | One contract covering a run of back to back voyages at one agreed rate. The subject of the simulator. |
| Time charter | Hiring the ship itself for a period at a daily hire rate. The charterer directs it and buys the fuel. |
| Laycan | Laydays and cancelling. The window in which the ship must show up to load. |
| Laytime | The free time allowed for loading and discharging before the clock starts costing money. |
| Demurrage | What the charterer pays the owner, per day, when the ship is held beyond laytime. |
| Despatch | The reverse of demurrage. The owner pays the charterer for finishing early. |
| Laden | Loaded with cargo. |
| Ballast | Sailing empty, carrying seawater for stability. The return leg of most voyages. |
| Deadheading | Running empty without earning. What the repositioning module is meant to minimise. |
| Bunkers | The ship's fuel. Bunkering is refuelling. |
| Lighterage | Taking cargo off a big ship into barges at an anchorage, so it floats higher and can enter a shallow port. |
| Transshipment | Moving cargo from one vessel to another before it reaches the final berth. |
| Anchorage | A marked sea area where ships anchor to wait or to work cargo. |
| Berth | The spot at the quay where a ship ties up. |
| Tidal window | The period around high tide when a deep ship can safely cross a shallow approach. |
| Congestion | The queue of ships waiting for a free berth. |
| Dry bulk | Unpackaged commodity carried loose in the hold. Coal, iron ore, grain, bauxite. |

**The measurements**

| Short form | Full name | What it does here |
|---|---|---|
| DWT | Deadweight tonnage | Total weight a ship can carry. Defines the size classes. |
| LOA | Length overall | The ship's full length. Berths have a hard limit on it. |
| Beam | Beam | The ship's width. |
| Draft | Draft, or draught | How deep the hull sits below the waterline. Loaded ships sit deeper. |
| UKC | Under keel clearance | The water gap between the keel and the seabed that a port insists on. |
| TPC | Tonnes per centimetre immersion | How many tonnes change the draft by one centimetre. Converts a depth shortfall into a lighterage tonnage. |
| MT, T | Metric tonne | One thousand kilograms. Freight is quoted in dollars per tonne. |
| TPD | Tonnes per day | How fast a port can load or discharge. |
| nm | Nautical mile | Sea distance. One nautical mile is 1,852 metres. |
| kt | Knot | One nautical mile per hour. |
| TAT | Turn around time | Arrival to departure, including the wait for a berth. |
| VLSFO | Very low sulphur fuel oil | The standard marine fuel since the sulphur cap of 2020. |
| BAF | Bunker adjustment factor | A clause that shares fuel price moves between owner and charterer against an agreed basis price. |

**The ship classes, smallest to largest**

| Class | Roughly | Why the name, and where it fits |
|---|---|---|
| Handysize | 28k to 40k DWT | Small and flexible. Gets into almost every East Coast port, including the shallow ones. |
| Supramax | 50k to 60k DWT | The workhorse. Usually carries its own cranes, so it does not need shore equipment. |
| Panamax | 65k to 80k DWT | Built to the width of the original Panama Canal locks. |
| Capesize | 100k DWT and up | Too big for the canals historically, so it sailed round the Cape of Good Hope. Only the deepest Indian ports take it. |

**The market**

| Short form | Full name | What it is |
|---|---|---|
| BDI | Baltic Dry Index | A daily composite of dry bulk freight rates published by the Baltic Exchange in London. The headline barometer for the trade. |
| BPI | Baltic Panamax Index | The Panamax slice of the same family. There are Capesize, Supramax and Handysize equivalents. |
| Forward curve | Forward curve | What the market currently believes future freight will cost. |
| FFA | Forward freight agreement | The traded contract used to hedge freight, the instrument behind a forward curve. |

**The ports in the data**

Discharge, all East Coast India: Paradip and Dhamra and Gopalpur in Odisha, Visakhapatnam and Gangavaram in Andhra Pradesh, Haldia in West Bengal, and Sagar or Sandheads, which is not a port but the anchorage at the mouth of the Hooghly where ships lighten before going upriver. Gangavaram is the deepest. Haldia and Gopalpur are the shallow problem children.

Loading: Newcastle, Gladstone and Abbot Point in Australia, Hampton Roads in the United States, Beira and Nacala in Mozambique, Murmansk in Russia, Kalimantan and Balikpapan in Indonesia.

**The statistics inside the engine**

| Term | What it does |
|---|---|
| Confidence interval | The band around a forecast. Here it is a 90% band, meaning the true rate should land inside it nine times in ten. |
| Standard deviation | How wide the spread of possible outcomes is. |
| CDF, cumulative distribution function | Gives the probability of landing below a given value. This is what produces the "chance spot wins" figure. |
| PDF, probability density function | The height of the bell curve. It draws the shape on the break-even chart. |
| Mean reversion | The tendency of freight rates to get pulled back toward a normal level rather than wandering forever. |
| Haversine | The formula for distance between two points on a sphere, used for sailing distance from port coordinates. |
| Correlation | How much forecast errors in different months move together. Set high here, because they do. |

**The rest**

AIS is the Automatic Identification System, the transponder every commercial ship broadcasts its position on, and the basis of any live vessel tracking. GIS means geographic information system, in practice the map. SIH is the Smart India Hackathon, and this is problem statement 26006. A crore is ten million rupees, written Cr, and a lakh is one hundred thousand. On the software side it is React with TypeScript, built by Vite, charts by Recharts, map by Leaflet, icons by Lucide, linting by oxlint.

Want this as a page you can keep open beside the code and share with the team?
