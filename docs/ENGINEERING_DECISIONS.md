# Engineering Decisions

I built a competitive-intelligence engine for pharma: it reads dense industry documents, pulls them into a structured model of drugs, trials, and regulatory events, and answers competitive questions with cited output, all measured by an offline evaluation harness. This document isn't about how the system works. It's about how I made decisions while building it. Three principles ran through all of it.

## 1. Build the evidence before you act on it

I don't optimize, add complexity, or tune anything until I have a measurement that says it's worth doing. This sounds obvious and almost nobody does it, because building the measurement first is slower and less satisfying than building the thing.

The labeled answer set, the scorer, and the baseline reports all existed before I wrote a line of the retrieval system they were meant to judge. Until "is this better?" is a question I can answer with a number, every improvement is a guess.

That ordering paid off directly. The retrieval system has two parts: a reliable baseline and a more sophisticated layer on top. The obvious story is "the sophisticated layer helps." Because I'd built the baseline and its evaluation first, I didn't have to assume that story, I could test it. I measured the second layer as a difference against the baseline, and the evaluation showed a real gain, so its value was a number I could defend rather than a hope. I'd also written down, in advance, that "it adds nothing" would be an acceptable result. If you only build things you've already decided are good, you can't learn anything from them. Building the baseline first is what turned that layer from an assumption into a measured result, which is the only version of the work that means anything.

## 2. Refuse knobs you can't justify

Every tunable parameter is a promise that you can set it correctly. If your evidence can't tell you the right setting, the knob isn't sophistication. It's a system that looks tuned while it's guessing. My rule: if the data can't resolve a parameter, it doesn't go in, and the limitation gets reported instead of hidden.

The clearest case prevented a misleading number. Combining two retrieval methods usually calls for a tunable weight controlling how much each one counts. My evaluation set had nine scored queries, far too few to set that weight without fitting it to noise, so any value would have looked principled and meant nothing. I used a weighting-free method instead and said why. With nine queries, there was no honest way to claim a tuned weight was better than a default, and skipping it cost me nothing the evidence could detect.

A second knob justified the rule even more directly, because the data later proved it was never needed. I'd deferred a decision on a similarity threshold, planning to tune it later. The measurements came back bimodal, either a clean match or no match, with no middle ground for a threshold to act on. The threshold I'd been prepared to agonize over turned out to be inert, so I reported it as inert instead of inventing a calibration. A later fix needed a fixed slot count I also couldn't justify, and I refused that one too. Three decisions, one rule: a knob you can't set from evidence stays out.

The same instinct applied to a metric. I had open-ended fields like "therapeutic area" that I could have scored for accuracy, but there's no standard taxonomy for them, so scoring them would mean inventing one and grading the system against my own invention. I reported those fields descriptively instead of turning them into a number that looked rigorous and measured nothing.

## 3. Localize before you solve

A bad aggregate number is almost never bad everywhere. Before I fix a low score, I break it down to find where the failure actually lives, because the fix for a localized problem is nothing like the fix for a diffuse one, and most improvements aimed at an average miss the real cause.

One extraction score, for regulatory events, came back around 0.41, low enough to look like a broken component. I traced it instead of treating it as general weakness. The misses weren't spread across the corpus. They concentrated in one pattern: the model read the status cells of a particular kind of table as a different category of fact. Everywhere else it performed fine. So 0.41 wasn't a grade on the component, it was a diagnosis of one failure mode, which told me the fix was narrow and specific rather than a general overhaul.

The clearest payoff came on the retrieval side, where the diagnosis led straight to an architectural decision and the later evaluation landed exactly where the diagnosis predicted. Broken down by question type, the baseline was strong on direct factual lookups and weak on questions that gather scattered facts from across a document. That split was the whole signal: the weakness sat exactly where a structured, fact-level retrieval layer should help, since structured facts concentrate what long passages dilute. So I built that layer to target those questions. The follow-up evaluation closed the loop: clear gains on the aggregate and comparison questions the baseline handled worst, and little change where it was already strong. The improvement showed up precisely where localization said it would, which is the difference between a fix aimed at evidence and a fix aimed at a hunch.

Localizing also tells you when not to reach for code. At one point two goals were structurally in tension: improving the combined system on one axis necessarily hurt it on another, and no fix I could justify resolved it. So I let the architecture absorb the conflict. I'd built one component as a dependable fallback, and it covered the case the combined system couldn't. Some problems aren't tuning problems, and once you've localized them you can see the right answer is structural.

## The thread

These aren't three habits, they're one: let evidence drive the decisions, especially at a scale where most signals are noise and the easy move is to trust intuition instead of measurement. Build the measurement first, refuse the parameters it can't support, trace every number to where it comes from. The discipline isn't in the tools. It's in being honest about what you actually know.
