#include <stdio.h>
#include <string.h>

#include "../main/camera_preview.h"

int main(void)
{
    char url[80];

    if (!camera_preview_make_url(url, sizeof(url), "192.168.137.23", 8080)) {
        printf("URL formatting unexpectedly failed\n");
        return 1;
    }
    if (strcmp(url, "http://192.168.137.23:8080/capture.jpg") != 0) {
        printf("unexpected URL: %s\n", url);
        return 1;
    }
    if (camera_preview_make_url(url, sizeof(url), "", 8080) ||
        camera_preview_make_url(url, sizeof(url), "192.168.137.23", 0)) {
        printf("invalid endpoint accepted\n");
        return 1;
    }
    return 0;
}
