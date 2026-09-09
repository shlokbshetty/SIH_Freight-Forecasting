# SIH_Freight-Forecasting
An intelligent freight forecasting and optimization platform leveraging ML time-series models, AIS vessel tracking, and port draft constraints to optimize bulk cargo procurement for East Coast Indian ports.

26006
Problem Statement Title	
Development of an Intelligent Freight Forecasting Model for Optimized Vessel Chartering and Bulk Cargo Procurement from overseas to East Coast of India
Description	
Background:

The current approach to vessel chartering for bulk cargo procurement to India's East Coast ports often involves daily market exploration, leading to reactive decision-making and likely missed opportunities for cost savings and efficiency. The highly volatile nature of global freight markets, coupled with varying supply and demand dynamics from key origins like Australia, the US, Mozambique, Russia and Indonesia, makes it challenging to identify optimal entry points for short-term or mid-term charter contracts. Furthermore, without a robust future forecasting mechanism, determining the most suitable vessel type (e.g., Handysize, Supramax, Panamax,Capesize) for specific cargo parcels and routes, while accounting for port infrastructure limitations at both origin and destination, results in suboptimal utilization and increased idle time. This manual, market-dependent approach requires analytics to mitigate risks associated with freight fluctuations and port-specific constraints, directly impacting overall logistics costs and supply chain reliability. Detailed Description:

The problem statement addresses the critical need for a sophisticated freight forecasting model to revolutionize vessel chartering and bulk cargo procurement for East Coast Indian ports. Currently, our operations are heavily reliant on daily engagements with the freight market. This traditional method leads to several inefficiencies: a lack of predictive insight into future freight rates, making it difficult to secure favorable short-term or mid-term charter contracts; an inability to proactively identify the optimal time to enter the market for specific vessel types and cargo sizes; and significant challenges in minimizing vessel idle time due to inadequate planning regarding port-specific infrastructure restrictions.

For instance, procuring bulk cargo (such as coal) from Australia, the US,Mozambique, and Indonesia presents unique logistical challenges. Each origin-destination pair has distinct sailing distances, trade lane dynamics, and, crucially,varying port capabilities. East Coast Indian ports, like Paradip, Vizag, Gangavaram,Gopalpur, Dhamra, Sagar- Sandheads and Haldia, each possess specific draft restrictions, berthing limitations, and cargo handling capacities that dictate the maximum permissible vessel size and turnaround time.The proposed system should therefore integrate multiple data points for comprehensive analysis. This includes historical freight rate data for various vessel sizes across relevant trade routes, global economic indicators, commodity price trends, seasonal variations in demand and supply, and real-time port congestion information for both origin and destination ports. Furthermore, it must incorporate detailed infrastructure constraints of Indian East Coast ports, such as maximum LOA (Length Overall), beam, draft, and cargo handling rates, along with similar data for the loading ports in Australia, the US, Mozambique, and Indonesia.

Expected Solution:

The expected solution is the development and implementation of an intelligent, datadriven Freight Forecasting Model. This model should leverage advanced analytical techniques, potentially including machine learning algorithms (e.g., time series forecasting, regression models) and artificial intelligence, to predict future freight rates with a high degree of accuracy for various vessel types and trade routes. The solution should offer actionable insights by providing recommendations on:

a. Optimal Market Entry Timing: Identify ideal windows to secure short-term or mid-term vessel charter contracts for specific cargo requirements, minimizing freight costs.

b. Vessel Type Optimization: Recommend the most suitable vessel type (e.g.,Handysize, Supramax, Panamax, Capesize) for a given cargo volume and origin-destination pair, considering all known port infrastructure limitations at both loading and discharge ports on India's East Coast. This includes factoring in draft restrictions, LOA, and cargo handling capabilities to prevent idle time and ensure efficient turnaround.

c. Idle Scenario Management: Propose strategies for minimizing vessel idle time by forecasting periods of low demand and suggesting alternative employment opportunities or optimized positioning to reduce deadheading.

d. Risk Mitigation: Provide early warnings for potential market volatility, port congestion, or other disruptions that could impact chartering decisions.

The model should be user-friendly, perhaps with a dashboard interface, allowing logistics managers to input cargo details, origin/destination ports, and desired contract duration to receive comprehensive freight forecasts and actionable recommendations.The ultimate goal is to move from a reactive, daily market approach to a proactive, predictive chartering strategy, leading to significant cost reductions, improved supply chain efficiency, and enhanced decision-making capabilities.

Objective:

Development of model to facilitate moving from multiple single spot contracts being entered into currently to short term / medium term multiple voyage contracts.


## **Core UI Features & Feature Map**

#### **1. Interactive GIS Maritime Map (Primary Visual Anchor)**

* **Live Vessel & Port Tracking Overlay:** Interactive global map showing loading ports (Australia, US, Mozambique, Indonesia, Russia) and East Coast Indian discharge ports (Paradip, Vizag, Gangavaram, Gopalpur, Dhamra, Sagar-Sandheads, Haldia).
* **Geofenced Port Restrictions:** Color-coded status markers for discharge ports reflecting current draft availability, tide status, berth availability, and congestion level.
* **Route & Weather Layer:** Real-time routing showing sailing distances, estimated transit times, and weather/monsoon alerts along trade corridors.
* **Vessel Positioning Heatmap:** Visual representation of available vessel fleet density (Handysize, Supramax, Panamax, Capesize) across major trade routes to spot supply overages or shortages.

#### **2. Multi-Period Freight Forecasting Dashboard**

* **Rate Prediction Curve:** Time-series charts comparing spot rate trends against 1-month, 3-month, and 6-month forecasted rates per vessel type (e.g., Baltic Dry Index / Baltic Panamax Index integration).
* **Spot vs. Consecutive Voyage Charter (CVC) Evaluator:** Visual cost delta bar showing cumulative cost comparison between booking multiple spot contracts versus locking in a short/medium-term voyage contract.
* **Volatility & Sentiment Gauge:** Real-time risk indicator incorporating macro indicators (fuel/bunker prices, global commodity demand, macro-economic indices).

#### **3. Cargo & Port Compatibility Matrix (Vessel Selection Engine)**

* **Draft & Infrastructure Filter:** Automated feasibility check matching cargo volume and vessel specs against origin and destination port constraints:
* *Max Draft vs. Current Tidal Allowance*
* *Length Overall (LOA) & Beam Limits*
* *Cargo Discharge Rates (Tons/Day)*


* **Lighterage & Transshipment Alert:** Automatic notification if a Capesize/Panamax requires lighterage at Sagar/Sandheads before proceeding to shallow-draft ports like Haldia.

#### **4. Market Entry Window & Timing Recommendation Module**

* **Optimal Contract Window Identifier:** AI-driven calendar highlighting "Best Buy/Charter" windows (Green: Ideal entry; Yellow: Neutral; Red: High market volatility).
* **Forward Curve Analyzer:** Dynamic scenarios showcasing projected savings when locking contracts today vs. delaying entry by 1 to 4 weeks.

#### **5. Idle Scenario & Vessel Repositioning Planner**

* **Deadheading & Ballast Minimizer:** Recommendations for positioning vessels or selecting charter-out options during low-demand periods.
* **Turnaround Time (TAT) Predictor:** Estimated berth wait time + unloading time calculations to project total turn-around time per port.

#### **6. Contract Structuring & Scenario Builder (What-If Analysis)**

* **Contract Type Comparison:** Side-by-side simulator for Single Spot vs. Consecutive Voyage Contracts (CVC) vs. Period Time Charters.
* **Multi-Port Discharge Optimizer:** Split-cargo loading/unloading scenario generator (e.g., loading in Australia, discharging part cargo at Vizag and remaining at Paradip).

---

### **UI Architecture Framework**

| UI Dashboard Module | Primary User Action | Key Outputs & Visual Elements |
| --- | --- | --- |
| **Command Center (Home)** | High-level operational monitoring | Active contracts, live rate alerts, market trend tickers, map overview. |
| **Interactive Route Map** | Route planning & port congestion inspection | GIS Map, port markers, weather overlays, vessel density heatmaps. |
| **Forecast & Analytics** | Strategic contract timing analysis | Multi-line time-series graphs, forward curve projections, accuracy confidence intervals. |
| **Vessel & Port Matcher** | Feasibility checking & vessel selection | Dropdown inputs (Cargo weight, Origin, Destination) $\rightarrow$ Ranked vessel recommendations with constraint flags. |
| **Contract Simulator** | Contract structure selection | Cost comparison tables (Spot vs. Multi-Voyage), sensitivity sliders (bunker prices, demurrage rates). |
| **Risk & Alert Center** | Risk mitigation and proactive planning | Real-time notifications for port delays, weather disruptions, and sudden freight spikes. |
