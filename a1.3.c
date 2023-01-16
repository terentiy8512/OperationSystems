/*
    The starting program to use for Operating Systems Assignment 1 2021
    written by Robert Sheehan

    Modified by: Vadim Reger
    UPI: vreg113

    By submitting a program you are claiming that you and only you have made
    adjustments and additions to this code.
 */

#include <stdio.h> 
#include <stdlib.h> 
#include <unistd.h>
#include <string.h>
#include <sys/resource.h>
#include <stdbool.h>
#include <sys/times.h>
#include <time.h>
#include <math.h>

#define SIZE    16

struct size_and_data {
    int size;
    int *data;
};

struct bin_info {
    int size;
    int *data;
};

void print_data(struct size_and_data array) {
    for (int i = 0; i < array.size; ++i)
        printf("%d ", array.data[i]);
    printf("\n");
}

/* Check to see if the data is sorted. */
bool is_sorted(struct size_and_data array) {
    bool sorted = true;
    for (int i = 0; i < array.size - 1; i++) {
        if (array.data[i] > array.data[i + 1])
            sorted = false;
    }
    return sorted;
}

/* Fill the array with random data. */
void produce_random_data(struct size_and_data array) {
    srand(1); // the same random data seed every time
    for (int i = 0; i < array.size; i++) {
        array.data[i] = rand() % 1000;
    }
}

/* Split the data into 4 bins. */
void split_data(struct size_and_data array, struct bin_info bins[]) {
    for (int i = 0; i < array.size; i++) {
        int number = array.data[i];
        if (number < 250) {
            bins[0].data[bins[0].size++] = number;
        } else if (number < 500) {
            bins[1].data[bins[1].size++] = number;
        } else if (number < 750) {
            bins[2].data[bins[2].size++] = number;
        } else {
            bins[3].data[bins[3].size++] = number;
        }
    }
}

/* Allocate space for the data or a bin. */
int *allocate(int size) {
    int *space;
    space = (int *)calloc(size, sizeof(int));
    if (space == NULL) {
        perror("Problem allocating memory.\n");
        exit(EXIT_FAILURE);
    }
    return space;
}

/* Move the data from the bins back to the original array. */
void move_back(struct size_and_data array, struct bin_info bins[]) {
    for (int bin = 0; bin < 4; bin++) {
        for (int i = 0; i < bins[bin].size; i++) {
            *array.data++ = bins[bin].data[i];
        }
    }
}

/* The slow insertion sort. */
void insertion(struct bin_info bin) {
    for (int i = 1; i < bin.size; i++) {
        for (int j = i; j > 0; j--) {
            if (bin.data[j-1] > bin.data[j]) {
                int temp;
                temp = bin.data[j];
                bin.data[j] = bin.data[j-1];
                bin.data[j-1] = temp;
            } else {
                break;
            }
        }
    }
}

int main(int argc, char *argv[]) {
    struct size_and_data the_array;
    struct bin_info bins[4];

    // creating pipes to communicate with child proccesses
    int pipe1[2]; 
    int pipe2[2]; 
    int pipe3[2]; 

    if (pipe(pipe1) == -1){
        perror("Problem creating the pipe.\n");
        exit(EXIT_FAILURE);
    }
    if (pipe(pipe2) == -1){
        perror("Problem creating the pipe.\n");
        exit(EXIT_FAILURE);
    }
    if (pipe(pipe3) == -1){
        perror("Problem creating the pipe.\n");
        exit(EXIT_FAILURE);
    }


	if (argc < 2) {
		the_array.size = SIZE;
	} else {
		the_array.size = pow(2, atoi(argv[1]));
	}

    the_array.data = allocate(the_array.size);
    for (int i = 0; i < 4; i++) {
        bins[i].size = 0;
        bins[i].data = allocate(the_array.size);
    }

    produce_random_data(the_array);

    if (the_array.size < 1025)
        print_data(the_array);

    struct tms start_times, finish_times;
    time_t start_clock, finish_clock;

    start_clock = time(NULL);
    times(&start_times);
    printf("start time in clock ticks: %ld\n", start_times.tms_utime);

    split_data(the_array, bins);

    // ------------ TOTAL BINS ------------
    int sum = 0;
    for (int i = 0; i < 4; i++) {
        sum += bins[i].size;
    }
    printf("Total size of bins: %d\n", sum);


    int n1 = fork();
    int n2 = fork();
  
    
    if (n1 > 0 && n2 > 0) { // parent process
        close(pipe1[1]);
        close(pipe2[1]);
        close(pipe3[1]);

        insertion(bins[0]);

        if(read(pipe1[0], bins[1].data, sizeof(int) * bins[1].size) == -1){
                perror("Problem reading to pipe.\n");
                exit(EXIT_FAILURE);
        }
        if(read(pipe2[0], bins[2].data, sizeof(int) * bins[2].size) == -1){
                perror("Problem reading to pipe.\n");
                exit(EXIT_FAILURE);
        }
        if(read(pipe3[0], bins[3].data, sizeof(int) * bins[3].size) == -1){
                perror("Problem reading to pipe.\n");
                exit(EXIT_FAILURE);
        }
        
    }
    else if (n1 == 0 && n2 > 0) // child proccess
    {   
        close(pipe1[0]);
        close(pipe2[0]);
        close(pipe2[1]);
        close(pipe3[0]);
        close(pipe3[1]);

        insertion(bins[1]);

        if (write(pipe1[1], bins[1].data, sizeof(int) * bins[1].size) == -1){
            perror("Problem writing to pipe.\n");
            exit(EXIT_FAILURE);
        }
    }
    else if (n1 > 0 && n2 == 0) // child 2 proccess
    {
        close(pipe1[0]);
        close(pipe1[1]);
        close(pipe2[0]);
        close(pipe3[0]);
        close(pipe3[1]);

        insertion(bins[2]);

        if (write(pipe2[1], bins[2].data, sizeof(int) * bins[2].size) == -1){
            perror("Problem writing to pipe.\n");
            exit(EXIT_FAILURE);
        }
    }
    else { // child 3 proccess (grandchild)
        close(pipe1[0]);
        close(pipe1[1]);
        close(pipe2[0]);
        close(pipe2[1]);
        close(pipe3[0]);

        insertion(bins[3]);

        if (write(pipe3[1], bins[3].data, sizeof(int) * bins[3].size) == -1){
            perror("Problem writing to pipe.\n");
            exit(EXIT_FAILURE);
        }
    }


    if (n1 > 0 && n2 > 0){ // execute only for parent proccess

        move_back(the_array, bins);

        times(&finish_times);
        finish_clock = time(NULL);
        printf("finish time in clock ticks: %ld\n", finish_times.tms_utime);
        printf("Total elapsed time in seconds: %ld\n", finish_clock - start_clock);

        if (the_array.size < 1025)
            print_data(the_array);

        printf(is_sorted(the_array) ? "sorted\n" : "not sorted\n");

        free(the_array.data);
        for (int i = 0; i < 4; i++) {
            free(bins[i].data);
        }
    }
    exit(EXIT_SUCCESS);
}