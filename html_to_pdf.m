#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <WebKit/WebKit.h>

@interface PDFRenderer : NSObject <NSApplicationDelegate, WKNavigationDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) WKWebView *webView;
@property(nonatomic, strong) NSURL *sourceURL;
@property(nonatomic, strong) NSURL *outputURL;
@property(nonatomic, assign) BOOL finished;
@property(nonatomic, assign) NSInteger readinessChecks;
@end

@implementation PDFRenderer

- (void)generatePDF {
    WKPDFConfiguration *config = [[WKPDFConfiguration alloc] init];
    [self.webView createPDFWithConfiguration:config completionHandler:^(NSData * _Nullable data, NSError * _Nullable error) {
        if (error || data.length == 0) {
            fprintf(stderr, "pdf generation failed: %s\n", [[error localizedDescription] UTF8String]);
            [NSApp terminate:nil];
            return;
        }
        NSError *writeError = nil;
        [data writeToURL:self.outputURL options:NSDataWritingAtomic error:&writeError];
        if (writeError) {
            fprintf(stderr, "pdf write failed: %s\n", [[writeError localizedDescription] UTF8String]);
        }
        self.finished = YES;
        [NSApp terminate:nil];
    }];
}

- (void)waitUntilReadyAndGenerate {
    self.readinessChecks += 1;
    if (self.readinessChecks > 120) {
        [self generatePDF];
        return;
    }

    [self.webView evaluateJavaScript:@"window.__PDF_READY__ === true" completionHandler:^(id _Nullable result, NSError * _Nullable error) {
        if (!error && [result respondsToSelector:@selector(boolValue)] && [result boolValue]) {
            [self generatePDF];
            return;
        }
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(300 * NSEC_PER_MSEC)), dispatch_get_main_queue(), ^{
            [self waitUntilReadyAndGenerate];
        });
    }];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    self.webView = [[WKWebView alloc] initWithFrame:NSMakeRect(0, 0, 1200, 1600) configuration:config];
    self.webView.navigationDelegate = self;

    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1200, 1600)
                                              styleMask:NSWindowStyleMaskBorderless
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    self.window.releasedWhenClosed = NO;
    self.window.contentView = self.webView;
    [self.webView loadRequest:[NSURLRequest requestWithURL:self.sourceURL]];
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    self.readinessChecks = 0;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(250 * NSEC_PER_MSEC)), dispatch_get_main_queue(), ^{
        [self waitUntilReadyAndGenerate];
    });
}

- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    fprintf(stderr, "navigation failed: %s\n", [[error localizedDescription] UTF8String]);
    [NSApp terminate:nil];
}

- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    fprintf(stderr, "provisional navigation failed: %s\n", [[error localizedDescription] UTF8String]);
    [NSApp terminate:nil];
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 3) {
            fprintf(stderr, "usage: html_to_pdf <url> <output>\n");
            return 1;
        }

        NSString *urlString = [NSString stringWithUTF8String:argv[1]];
        NSString *outputPath = [NSString stringWithUTF8String:argv[2]];
        PDFRenderer *renderer = [[PDFRenderer alloc] init];
        renderer.sourceURL = [NSURL URLWithString:urlString];
        renderer.outputURL = [NSURL fileURLWithPath:outputPath];

        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyProhibited];
        app.delegate = renderer;
        [app run];

        return renderer.finished ? 0 : 1;
    }
}
