import timeit

# Simulated list of files
filenames = [f"disk_{i}.mp3" if i % 2 == 0 else f"file_{i}.txt" for i in range(100)]

def loop_method(files):
    audio_files = []
    for f in files:
        if f.endswith(".mp3"):
            audio_files.append(f)
    return audio_files

def comprehension_method(files):
    return [f for f in files if f.endswith(".mp3")]

def run_benchmark():
    iterations = 100000

    loop_time = timeit.timeit(lambda: loop_method(filenames), number=iterations)
    comp_time = timeit.timeit(lambda: comprehension_method(filenames), number=iterations)

    print(f"Loop method: {loop_time:.4f} seconds")
    print(f"List comprehension method: {comp_time:.4f} seconds")
    if loop_time > 0:
        print(f"Improvement: {(loop_time - comp_time) / loop_time * 100:.2f}%")

if __name__ == "__main__":
    run_benchmark()
