> English translation of [IDEA.md](IDEA.md). The Chinese original is kept unchanged as the source of truth.

# Pipeline

### Pipeline design principles

1. 



### Overall approach

It goes like this: first, the fusion peptide we want to design has a specific structure, containing a rigid part (Beta sheet) and a flexible part, and at the end there is also a hook made of 6 histidines (His-tag), which is crucial for properties such as protein aggregation.

We have three main raw materials for building the fusion peptide:
1. Silk fibroin (as the base scaffold, selected from the best sequence mined from the literature)
2. Linker
3. Functional peptide

The logic of combination is to take silk fibroin as the base, insert the functional peptide at different positions, and connect them at the contact points with a Linker. For example, a "functional peptide + Linker + silk fibroin" structure can be used, or a "silk fibroin + Linker + functional peptide + Linker + 6-histidine hook" structure. Note that the hook made of these 6 histidines must in any case be placed at the far right end of the sequence.

The whole screening and construction workflow is divided into three steps:

1. FASTA-based functional peptide evaluation
   We need to find suitable functional peptides from more than 20,000 peptide records, across three screening levels:
   (a) Threshold filtering: use microservices to detect the toxicity, hemolysis, and allergenicity scores of the peptides; those above the set thresholds (i.e., dangerous) are removed directly.
   (b) Ranking: evaluate against a specific function (such as antioxidant activity), rank the scores from 0 to 1 from high to low, and take the top 50% or the top 1000.
   (c) Weighted average: assign weights according to the importance of each tool's or microservice's score, compute a composite score, and finally select the top 50 functional peptides to enter the next step.

2. Fusion peptide construction and 3D structure generation
   Combine the 50 selected functional peptides, 6 Linkers, and 1 silk fibroin. Considering the position choices (functional peptide placed at the beginning, the end, or on both sides), there are three position schemes in total.
   Obtain all possible FASTA sequences by exhaustive enumeration (50 × 6 × 1 × 3), then submit them to tools such as AlphaFold or RoseTTAFold to predict their 3D structures and generate PDB files.

3. PDB-based evaluation
   Evaluate the fused protein. Use SASA (solvent-accessible surface area) to compute whether the functional peptide is buried or exposed in the structure, and combine with other microservice tools to complete the final performance evaluation.

But we do not necessarily have to follow these steps rigidly. In terms of viewpoint, philosophy, and methodology, although this is the workflow, the steps can be flexibly reordered.

Regarding threshold filtering, we can rank first and then filter, or filter first and then rank, or even perform multiple interleaved operations. Our final goal is to keep the number of fusion constructs submitted for 3D structure generation to within 50. Because 3D structure generation is extremely compute- and time-intensive, we cannot afford the delay — time is very tight.

Therefore, our design here follows one core principle: put the "light and fast" services that can process large volumes first, as much as possible. The whole design presents an inverted pyramid or funnel shape, and with each layer the number of candidate functional states participating in the computation decreases accordingly. Those heavy tasks that run slowly, take a long time, and have relatively large model weights are handled later.

The specific steps are as follows:
1. Score, screen, filter, and select the functional states based on FASTA. After this step, the number of candidates finally produced will be very limited.
2. Exhaustive enumeration plus 3D structure generation. The screening in the previous step ensures that the compute and time we spend in this step are not too large.
3. Final evaluation.

This is our overall design principle.






# Specific details

Now let me point out some specific design details that need to be considered:

1. Data loading and .env file control (though by the way, would it also work to put everything uniformly in config.py?)
   (a) During the testing stage there is no need to run all 20,000 records directly — that is absurd; at present our load_data step only performs partial loading.
   (b) What data is currently loaded (for example, right now only antioxidant peptide data is loaded) is completely hardcoded in the code, and finding it among hundreds of lines of code is very troublesome, even with indexing added.
   (c) Solution: write a .env file that explicitly specifies the data types we need to load.  

1. Caching mechanism
   (a) The importance of caching: we need to debug and test repeatedly, and failures may even interrupt us midway; in such cases sufficient caching is essential.
   (b) Scope of caching: whether files are large or small, once the data volume reaches thousands or tens of thousands, caching is needed.
   (c) Concrete example: for example, the PDB structures inferred by AlphaFold3 — we need to cache the corresponding files. If the FASTA sequence is exactly the same, call the cache directly on a re-test instead of running it again.
   (d) Storage path:
       - Option 1: place it under each tool's/microservice's own folder.
       - Option 2 (recommended): set up a shared cache pool. When deploying via Docker in production, everyone mounts the same location, and microservices search the cache they need.
   (e) Cache classification:
       - Microservice cache: the specific cache internal to each microservice.
       - Pipeline cache: cache the various possibilities produced by the whole workflow (such as the enumeration step), stored in a configuration folder under the project root directory.

1. So the third technical detail is about lifecycle, specifically AlphaFold. Because it consumes so much GPU memory, it is impossible for us to run AlphaFold together with other things, so GPU memory management must be done well.

    Regarding microservice startup, my Pipeline will certainly contain scheduling logic for microservices. We cannot open and load all models at the very beginning; otherwise GPU memory will explode before any work even starts.

    The scheme I envision is:
   1. Establish a low-footprint computing mode that starts services in sequence and shuts them down once they are done.
   2. Distinguish computing resources: if it is CPU computing, leaving it on all the time does not matter — it is actually more convenient and avoids the code complexity added by lifecycle management.
   3. Special handling for AlphaFold:
      (a) Before starting AlphaFold computation, all other microservices must be stopped and shut down.
      (b) Only after AlphaFold computation ends are subsequent operations with other microservices performed.

    If we do not handle this carefully, GPU memory really will explode.

    However, we are also considering whether to switch away from this AlphaFold or something else later on.

    For now, let's build the plan on this basis — let's go with this for now, okay?
