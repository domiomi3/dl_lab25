Install conda environment and activate it
```
conda env create -f env.yaml
conda activate mensa
```

Either run python script directly with specified dates:
```
python scrape.py --start 2024-11-30 --stop 2024-12-31 
```
or if you want to download more images starting with today's date:
```
sbatch run_scrape 200
```
where the argument specifies number of days to dowload from.
If you choose the latter, remeber to update global variables in the bash script.