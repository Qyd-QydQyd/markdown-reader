#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <arpa/inet.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <unistd.h>

static NSString * const kPythonBin = @"/usr/bin/python3";
static NSString * const kBindHost = @"127.0.0.1";
static NSString * const kDisplayHost = @"read-md.localhost";
static const int kPort = 8765;
static NSString * const kLauncherLog = @"/tmp/paper_reader_launcher.log";

static void appendLog(NSString *message) {
    NSString *line = [NSString stringWithFormat:@"%@ %@\n", [NSDate date], message];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:kLauncherLog];
    if (!handle) {
        [[NSFileManager defaultManager] createFileAtPath:kLauncherLog contents:nil attributes:nil];
        handle = [NSFileHandle fileHandleForWritingAtPath:kLauncherLog];
    }
    [handle seekToEndOfFile];
    [handle writeData:[line dataUsingEncoding:NSUTF8StringEncoding]];
    [handle closeFile];
}

static BOOL fileExists(NSString *path) {
    return path.length > 0 && [[NSFileManager defaultManager] fileExistsAtPath:path];
}

static NSString *resolveBundledResource(NSString *name, NSString *extension) {
    return [[NSBundle mainBundle] pathForResource:name ofType:extension];
}

static NSString *resolveServerScript(void) {
    NSString *envPath = [[[NSProcessInfo processInfo] environment] objectForKey:@"MD_READER_SCRIPT"];
    if (fileExists(envPath)) {
        return envPath;
    }

    NSString *bundled = resolveBundledResource(@"server", @"py");
    if (fileExists(bundled)) {
        return bundled;
    }

    NSString *cwdCandidate = [[NSFileManager defaultManager].currentDirectoryPath stringByAppendingPathComponent:@"md_reader/server.py"];
    if (fileExists(cwdCandidate)) {
        return cwdCandidate;
    }

    return nil;
}

static BOOL portIsListening(void) {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        return NO;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_len = sizeof(addr);
    addr.sin_family = AF_INET;
    addr.sin_port = htons(kPort);
    inet_pton(AF_INET, [kBindHost UTF8String], &addr.sin_addr);

    struct timeval timeout;
    timeout.tv_sec = 0;
    timeout.tv_usec = 700000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    BOOL connected = connect(sock, (struct sockaddr *)&addr, sizeof(addr)) == 0;
    close(sock);
    return connected;
}

static void startServer(NSString *documentPath) {
    appendLog([NSString stringWithFormat:@"startServer: %@", documentPath]);
    NSString *serverScript = resolveServerScript();
    if (!fileExists(serverScript)) {
        appendLog(@"startServer failed: server.py not found");
        return;
    }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:kPythonBin];
    task.arguments = @[serverScript, @"--host", kBindHost, @"--port", [NSString stringWithFormat:@"%d", kPort], @"--file", documentPath];
    NSString *logPath = @"/tmp/md_reader.log";
    [[NSFileManager defaultManager] createFileAtPath:logPath contents:nil attributes:nil];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:logPath];
    task.standardOutput = handle;
    task.standardError = handle;
    [task launch];
}

static void openReader(NSString *documentPath) {
    appendLog([NSString stringWithFormat:@"openReader: %@", documentPath]);
    NSString *encodedPath = [documentPath stringByAddingPercentEncodingWithAllowedCharacters:[NSCharacterSet URLQueryAllowedCharacterSet]];
    NSString *urlString = [NSString stringWithFormat:@"http://%@:%d/?path=%@", kDisplayHost, kPort, encodedPath];
    [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:urlString]];
}

@interface PaperReaderDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, assign) BOOL handledOpenEvent;
@property(nonatomic, strong) NSString *startupDocument;
@end

@implementation PaperReaderDelegate

- (void)openDocumentPath:(NSString *)documentPath {
    if (!fileExists(documentPath)) {
        appendLog([NSString stringWithFormat:@"openDocumentPath missing: %@", documentPath]);
        return;
    }
    appendLog([NSString stringWithFormat:@"openDocumentPath: %@", documentPath]);
    self.handledOpenEvent = YES;
    [NSApp activateIgnoringOtherApps:YES];
    if (!portIsListening()) {
        startServer(documentPath);
        [NSThread sleepForTimeInterval:1.0];
    }
    openReader(documentPath);
    [NSApp terminate:nil];
}

- (NSString *)fallbackDocument {
    return nil;
}

- (NSString *)pickDocumentWithPanel {
    appendLog(@"pickDocumentWithPanel");
    [NSApp activateIgnoringOtherApps:YES];
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.title = @"选择论文 Markdown 文件";
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    panel.allowedFileTypes = @[@"md", @"markdown", @"txt"];
    if ([panel runModal] == NSModalResponseOK) {
        return panel.URL.path;
    }
    return [self fallbackDocument];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    appendLog(@"applicationDidFinishLaunching");
    [NSApp activateIgnoringOtherApps:YES];
    if (fileExists(self.startupDocument)) {
        [self openDocumentPath:self.startupDocument];
        return;
    }

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.25 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        if (self.handledOpenEvent) {
            return;
        }
        NSString *picked = [self pickDocumentWithPanel];
        if (picked.length > 0) {
            [self openDocumentPath:picked];
        } else {
            appendLog(@"no document selected, terminating");
            [NSApp terminate:nil];
        }
    });
}

- (void)application:(NSApplication *)sender openFiles:(NSArray<NSString *> *)filenames {
    appendLog([NSString stringWithFormat:@"openFiles: %@", filenames]);
    NSString *firstPath = filenames.firstObject;
    if (fileExists(firstPath)) {
        [self openDocumentPath:firstPath];
    } else {
        appendLog(@"openFiles failed");
        [sender replyToOpenOrPrint:NSApplicationDelegateReplyFailure];
    }
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        appendLog(@"main start");
        NSString *startupDocument = nil;
        for (int i = 1; i < argc; i++) {
            if (argv[i] == NULL) {
                continue;
            }
            NSString *candidate = [NSString stringWithUTF8String:argv[i]];
            if ([candidate hasPrefix:@"-psn_"]) {
                continue;
            }
            if (fileExists(candidate)) {
                startupDocument = candidate;
                appendLog([NSString stringWithFormat:@"startupDocument arg: %@", startupDocument]);
                break;
            }
        }

        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        PaperReaderDelegate *delegate = [[PaperReaderDelegate alloc] init];
        delegate.startupDocument = startupDocument;
        app.delegate = delegate;
        appendLog(@"app run");
        [app run];
    }
    return 0;
}
