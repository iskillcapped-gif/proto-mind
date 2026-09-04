import Darwin
import Foundation

enum ChatHistoryFiles {
    static func stamp(_ url: URL) throws -> String {
        var info = stat()
        guard lstat(url.path, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else { throw ChatHistoryFormat.invalid() }
        return "\(info.st_dev):\(info.st_ino):\(info.st_size):\(info.st_mtimespec.tv_sec):\(info.st_mtimespec.tv_nsec):\(info.st_ctimespec.tv_sec):\(info.st_ctimespec.tv_nsec)"
    }

    static func read(_ url: URL, limit: Int = ChatHistoryFormat.fileLimit) throws -> Data? {
        let fd = Darwin.open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        if fd < 0 {
            if errno == ENOENT { return nil }
            throw failure("Не удалось открыть файл истории")
        }
        defer { Darwin.close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG, info.st_size >= 0, info.st_size < limit else {
            throw ChatHistoryFormat.invalid()
        }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        let data = try handle.read(upToCount: limit) ?? Data()
        var after = stat(), current = stat()
        guard fstat(fd, &after) == 0, lstat(url.path, &current) == 0, data.count == info.st_size,
              info.st_ino == current.st_ino, info.st_dev == current.st_dev,
              info.st_size == after.st_size, info.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              info.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec else { throw ChatHistoryFormat.invalid() }
        return data
    }

    static func directory(_ url: URL, create: Bool) throws {
        if create { try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
        var info = stat()
        guard lstat(url.path, &info) == 0, (info.st_mode & S_IFMT) == S_IFDIR else { throw ChatHistoryFormat.invalid() }
    }

    static func syncDirectory(_ url: URL) throws {
        let fd = Darwin.open(url.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw failure("Не удалось проверить папку истории") }
        defer { Darwin.close(fd) }
        guard fsync(fd) == 0 else { throw failure("Не удалось подтвердить сохранение истории") }
    }

    static func write(_ data: Data, to url: URL, replace: Bool) throws {
        let parent = url.deletingLastPathComponent()
        try directory(parent, create: true)
        let temporary = parent.appendingPathComponent(".pending-" + UUID().uuidString)
        let fd = Darwin.open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw failure("Не удалось создать файл истории") }
        defer { Darwin.close(fd); _ = unlink(temporary.path) }
        try FileHandle(fileDescriptor: fd, closeOnDealloc: false).write(contentsOf: data)
        guard fsync(fd) == 0 else { throw failure("Не удалось сохранить файл истории") }
        if replace {
            // Refuse a symlink or a non-file at the commit point.
            _ = try read(url, limit: ChatHistoryFormat.legacyLimit)
            guard rename(temporary.path, url.path) == 0 else { throw failure("Не удалось обновить историю") }
        } else if link(temporary.path, url.path) != 0 {
            guard errno == EEXIST, try read(url, limit: max(ChatHistoryFormat.fileLimit, data.count + 1)) == data else { throw ChatHistoryFormat.invalid() }
        }
        try syncDirectory(parent)
    }

    static func withLock<T>(in directory: URL, write: Bool, _ body: () throws -> T) throws -> T {
        if write { try self.directory(directory, create: true) }
        let url = directory.appendingPathComponent(".history.lock")
        let flags = (write ? O_RDWR | O_CREAT : O_RDONLY) | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC
        let fd = Darwin.open(url.path, flags, 0o600)
        if fd < 0 {
            if !write && errno == ENOENT { return try body() }
            throw failure("Не удалось проверить доступ к истории")
        }
        defer { Darwin.close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else { throw ChatHistoryFormat.invalid() }
        guard flock(fd, (write ? LOCK_EX : LOCK_SH) | LOCK_NB) == 0 else {
            throw NativeError.message("История сейчас сохраняется в другой копии Proto-Mind. Повторите после завершения записи.")
        }
        defer { flock(fd, LOCK_UN) }
        let result = try body()
        var current = stat()
        guard lstat(url.path, &current) == 0, current.st_ino == info.st_ino, current.st_dev == info.st_dev else { throw ChatHistoryFormat.invalid() }
        return result
    }

    static func failure(_ message: String) -> NativeError { .message(message + ": " + String(cString: strerror(errno))) }
}
