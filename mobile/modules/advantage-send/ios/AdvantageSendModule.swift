import ExpoModulesCore
import UIKit

public class AdvantageSendModule: Module {
  public func definition() -> ModuleDefinition {
    Name("AdvantageSend")
    Events("onChange")

    OnCreate {
      SendManager.shared.onChange = { [weak self] in self?.sendEvent("onChange", [:]) }
      SendManager.shared.wake()
    }

    AsyncFunction("start") { (options: SendOptions) in
      try SendManager.shared.start(options)
    }

    AsyncFunction("list") { () -> [[String: Any]] in
      SendManager.shared.list()
    }

    AsyncFunction("remove") { (jobId: String) in
      SendManager.shared.remove(jobId)
    }

    AsyncFunction("updateSignIn") { (session: String?, passcode: String?) in
      SendManager.shared.updateSignIn(session: session, passcode: passcode)
    }
  }
}

struct SendOptions: Record {
  @Field var jobId: String = ""
  @Field var title: String = ""
  @Field var filePath: String = ""
  @Field var apiBase: String = ""
  @Field var session: String? = nil
  @Field var passcode: String? = nil
  @Field var partBytes: Int = 32 * 1024 * 1024
  @Field var r2: Bool = true
}

// iOS wakes the app here when a background transfer needs attention.
public class SendAppDelegate: ExpoAppDelegateSubscriber {
  public func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    SendManager.shared.wake()
    return true
  }

  public func application(
    _ application: UIApplication,
    handleEventsForBackgroundURLSession identifier: String,
    completionHandler: @escaping () -> Void
  ) {
    SendManager.shared.backgroundEvents(identifier: identifier, done: completionHandler)
  }

  public func applicationDidBecomeActive(_ application: UIApplication) {
    SendManager.shared.wake()
  }
}
