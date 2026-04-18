# Questions for Ben

Check this file periodically. Answer inline or in a chat session — either works.
I'll date questions and mark answered ones.

ANSWERED!

---

## Open Questions

### Q1 (2026-04-18) — Alert Examples
For the intent classification research, it would be really helpful to have a few concrete examples:
- **2-3 recent alerts you DID follow up on** (what made them interesting?)
- **2-3 recent alerts you mentally dismissed** (what made them noise?)

Even just symbol + date + "this one was closing" or "this was chasing" would help me calibrate. I can look up the data myself.



### Q2 (2026-04-18) — Console Scroll-Back Pattern
You mentioned scrolling back to see alert details that aren't in the summary. What specific details are you looking for when you scroll? Is it the full alert line (strike, DTE, volume, etc.) or something else? This tells me what information is "worth scrolling for" — i.e., worth making more accessible.



### Q3 (2026-04-18) — Earnings Investigation Success
When you check a STRONG BUY signal on Robinhood, what makes you decide to buy vs pass? Have you traded any of the signals the system generated so far? Understanding what makes a signal "actionable enough to trade" vs "interesting but passed" would help me evaluate signal quality.



---

## Answered

### Q1 (2026-04-18) — Alert Examples

Ben: I'm addressing this assuming you mean FLOW alerts; not that you needed to specify but just to be clear, since earnigns technically has "alerts" too.
Here are some flow alerts I've followed and why:
id	    contract_hash            	trade_date
10767	DOW|37.5|2026-05-15|CALL	2026-04-17     - This one appeared on a day where oil stocks plummeted. DOW was down like 12% when this fired. It said to me "Whoever is buying this is buying the dip, and thats exactly what I need to do when an industry is hit like this." The plan was to capitalize on a reversion to the mean. It did; by end of day I sold for 23% profit. Vol/OI looked good, UL to Strike looked good, option price was accessible. Easy. Alert fired at 10:15am, I bought at 10:30am. (I bought for $1.25, sold at $1.53)
10780	DVN|45.0|2026-05-15|CALL	2026-04-17     - This one appealed to me too for the same reasons, another energy stock hit by bad news. That stock was down 8%, but the alert fired at 1:30pm, by which point the stock had already recovered 4% (so still down 4%). Did I miss out on a signal earlier? At end of day, this was up 10% (I bought for $1.54, day ended at $1.70)
10754	NU|15.0|2026-05-15|PUT	    2026-04-16     - I bought it at 10:37am for $0.69... this was actually at a trough that day. My option has been underwater until like 4pm Friday, and I think I'm up 1.45%. The vol/oi ratio was very enticing, and a $15 put with UL at $15.39 seems achievable. I'll sit on it a few more days and see what volatility brings me.
10736	CTRA|34.0|2026-05-15|CALL	2026-04-14     - This one I regret. But look at that Vol/OI - 15,000 EVEN was traded at the alert, clearly something big from someone smart. But I was wrong, for a few reasons. One, the system did NOT note that 3 other strikes had 15,000 contracts move; one at $36, one at like $44, and one at like $42. The $40+ ones were too far OTM to be included in our system; no idea why $36 didn't trigger. This looked like conviction and directionality. However, the next day OI was... actually, misleading on this table, beacuse I goofed and the morning Option Pipeline process started five minutes before tradier updated their data so the next-day OI should read more like 15,000... anyway next day OI showed that the 15,000 from 36 was CLOSING and this was OPENING indicating a roll downward - essentially maybe trying to recover from the price downturn it had been experiencing for some time now. ANyway, I interpreted it as a reversion to mean play, with easy chance of profit. I was right, but i overestimated the magnitude. I should have set the sell to 25% or even 20%, there was a brief moment where I could have collected on that. But i expected too much and I didn't sell, and friday the stock dropped like a stone, losing 8% in one morning. So now its pretty much worthless. I guess that COULD have been a win if i was more disciplined, so technically a win? If so, it was right for the wrong reasons, which may as well be considered wrong, idk. Maybe not?
10679	VST|175.0|2026-05-15|CALL	2026-04-09     - This one also had a sister alert at $170, seemed like good conviction. However, I lost 20% on this, ouch. The $170 was closing, this was opening, I didn'tknow that until next day. The thing is, there's value in waiting for next day to understand the true nature of an alert, but also, there's value in jumping in right away for a day trade. Hard to tell. I often see a dip on the second day recover by the third, which is more attractive, but also sortof a gamble. 
10515	SLB|50.0|2026-04-17|CALL	2026-03-23     - This one actually pretty interesting and perhaps a perfect ideal example of the system in action. Search this hash in the flow_alerts table to see what I mean. On 3/26 an alert fired for 18,000 contracts, with scan timestamp at 3:52pm - an end of day trade, tough to follow. I didn't see it until 4:03pm, after market close. SO I set a trade for the morning (3/24) and walked away. I bought 2 contracts at 9:31am for $2.09, a bit more expensive than their price of $1.89. By 10:19am that same day the price of the stock shot up to like $50 and the options were worth $2.63 - my 25% profit target, so I sold. Hurray! THe flow alerts show that two alerts happened that day for that same option: 6000 sold at 12:54pm, and 12000 at 1:42pm, the full 18000 traded in less than 5 trading hours. It looks like they sold at about $2.55 for both of them, which means I win! But its worth noting that by March 30 SLB rose to $53.54, so had I held on for a few more days, I could have seen 100% profit. But I can't let that thinking bother me, I sell and don't look back. but, then, how do I ever get a win larger than 25%? 

That's enough for now.


### Q2 (2026-04-18) — Console Scroll-Back Pattern

Ben: Ah, i just closed the display. The summary shows what alerrts fired, but not all details, like the actual contract. So i scroll up. Useful to see whats going on at symbol level though. Find what gets displayed in th orchestrator and compare what is shared and what isnt.

### Q3 (2026-04-18) — Earnings Investigation Success

I made a lot of money on PDD. I lost some money on ERIC. thats my sample so far. PDD was end of last earnings season. I focused on strong buy because it seemed like a better bet - why settle for buy when strong buy exists? but i hadnt tested the signals for reliability like you are. Helpful. What makes it worth following is: Cost (which is why i wont trade UNH despite strong buy), liquidity (ERIC probably wasnt liquid enough), historical move... honestly i dont have a mature understanding of this concept yet so i take an amateurish approach that needs good signals and practice and good advice, much of which comes with time.